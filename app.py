import os
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# Langchain
from langchain_community.document_loaders import UnstructuredMarkdownLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_classic.chains import create_retrieval_chain
from langchain_core.prompts import MessagesPlaceholder

# Langfuse
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler

import httpx
import requests

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -------------------------
# ENV
# -------------------------
load_dotenv()
VERIFY_TOKEN=os.getenv("VERIFY_TOKEN", "test")
PAGE_ID = os.getenv("PAGE_ID",1072166595975279)
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")

GRAPH_API_URL = f"https://graph.facebook.com/v25.0/{PAGE_ID}/messages"


# -------------------------
# Langfuse Initialization
# -------------------------
langfuse = Langfuse(
    public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
    secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
    host=os.getenv("LANGFUSE_BASE_URL")
)

langfuse_handler = CallbackHandler()


# -------------------------
# Load Knowledge Base
# -------------------------
loader = UnstructuredMarkdownLoader("pet_shop_les_orangers_ultra_pro_prod_kb.md")
documents = loader.load()

splitter = RecursiveCharacterTextSplitter(
    chunk_size=350,
    chunk_overlap=40
)

docs = splitter.split_documents(documents)

logger.info(f"KB chunks loaded: {len(docs)}")


# -------------------------
# Embeddings + Vector DB
# -------------------------
embeddings = HuggingFaceEmbeddings(
    model_name="BAAI/bge-small-en-v1.5",
    model_kwargs={"device": "cpu"}
)

vectorstore = FAISS.from_documents(docs, embeddings)

retriever = vectorstore.as_retriever(
    search_type="mmr",
    search_kwargs={
        "k": 4,
        "fetch_k": 10
    }
)

logger.info("Retriever ready")


# -------------------------
# LLM
# -------------------------
llm = ChatOpenAI(
    temperature=0,
    model="gpt-4o-mini"
)


store = {}

def get_session_history(session_id: str):
    if session_id not in store:
        store[session_id] = InMemoryChatMessageHistory()
        logger.info("new session_history created")
    return store[session_id]

# -------------------------
# Build Chain Dynamically
# -------------------------
def original_build_chain():

    langfuse_prompt = langfuse.get_prompt(
        "petshop-chatbot-prompt",
        label="production",
        cache_ttl_seconds=0
    )

    logger.info(f"Using prompt version: {langfuse_prompt.version}")
    prompt = ChatPromptTemplate.from_messages([
        ("system", langfuse_prompt.get_langchain_prompt()),
        MessagesPlaceholder(variable_name="chat_history"),  # ✅ CORRECT
        ("human", "{input}")
    ])
    document_chain = create_stuff_documents_chain(
        llm,
        prompt
    )

    # ✅ NEW STYLE retrieval chain
    qa_chain = create_retrieval_chain(
        retriever,
        document_chain
    )

    return qa_chain, langfuse_prompt


def build_chain():
    qa_chain, langfuse_prompt = original_build_chain()  # your existing logic

    chain_with_memory = RunnableWithMessageHistory(
        qa_chain,
        get_session_history,
        input_messages_key="input",
        history_messages_key="chat_history",
        output_messages_key="answer",  # ✅ CRITICAL FIX
    )

    return chain_with_memory, langfuse_prompt



# -------------------------
# FastAPI
# -------------------------
app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")


class ChatRequest(BaseModel):
    message: str


@app.get("/")
def read_root():
    return FileResponse("static/index.html")

def generate_response(user_message: str, session_id: str) -> str:
    qa_chain, langfuse_prompt = build_chain()

    response = qa_chain.invoke(
        {"input": user_message},
        config={
            "configurable": {
                "session_id": session_id  # 🔥 THIS ENABLES MEMORY
            },
            "callbacks": [langfuse_handler],
            "metadata": {
                "app": "petshop-chatbot",
                "prompt_version": langfuse_prompt.version
            },
            "tags": ["rag", "petshop"]
        }
    )

    return response["answer"]
# -------------------------
# Chat Endpoint
# -------------------------
@app.post("/chat")
async def chat(req: ChatRequest):
    answer = generate_response(req.message, session_id="default-user")
    return {"response": answer}

@app.get("/webhook")
async def verify(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode and token:
        if mode == "subscribe" and token == VERIFY_TOKEN:
            
            logger.info("WEBHOOK_VERIFIED")
            return PlainTextResponse(content=challenge, status_code=200)
        else:
            return PlainTextResponse("Forbidden", status_code=403)

async def send_message(psid: str, text: str):
    payload = {
        "recipient": {"id": psid},
        "messaging_type": "RESPONSE",
        "message": {"text": text}
    }

    params = {
        "access_token": PAGE_ACCESS_TOKEN
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(GRAPH_API_URL, json=payload, params=params)
        logger.info(f"SEND API RESPONSE: {response.text}")



@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()

    logger.info(f"EVENT_RECEIVED: {data}")
    if data.get("object") == "page":
        for entry in data.get("entry", []):
            for messaging in entry.get("messaging", []):

                sender_id = messaging.get("sender", {}).get("id")  # ✅ PSID
                message = messaging.get("message")

                if message and sender_id:
                    user_text = message.get("text", "")
                    
                    logger.info(f"USER MESSAGE:, {user_text}")
                    logger.info(f"PSID: {sender_id}")

                    # 🤖 Generate AI response
                    bot_reply = generate_response(user_text)

                    # 🔁 Reply
                    await send_message(sender_id, bot_reply)

    return PlainTextResponse("EVENT_RECEIVED", status_code=200)