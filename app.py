import os
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# Langchain
from langchain_community.document_loaders import UnstructuredMarkdownLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from langchain_classic.chains import create_retrieval_chain
from langchain_classic.chains.combine_documents import create_stuff_documents_chain

# Langfuse
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler

import requests

# -------------------------
# ENV
# -------------------------
load_dotenv()

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

print("KB chunks loaded:", len(docs))


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

print("Retriever ready")


# -------------------------
# LLM
# -------------------------
llm = ChatOpenAI(
    temperature=0,
    model="gpt-4o-mini"
)


# -------------------------
# Build Chain Dynamically
# -------------------------
def build_chain():

    # Fetch latest prompt from Langfuse
    langfuse_prompt = langfuse.get_prompt(
        "petshop-chatbot-prompt",
        label="production",
        cache_ttl_seconds=0
    )

    print("Using prompt version:", langfuse_prompt.version)

    prompt = ChatPromptTemplate.from_template(
        langfuse_prompt.get_langchain_prompt()
    )

    document_chain = create_stuff_documents_chain(
        llm,
        prompt
    )

    qa_chain = create_retrieval_chain(
        retriever,
        document_chain
    )

    return qa_chain, langfuse_prompt


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


# -------------------------
# Chat Endpoint
# -------------------------
@app.post("/chat")
def chat(req: ChatRequest):

    qa_chain, langfuse_prompt = build_chain()

    response = qa_chain.invoke(
        {
            "input": req.message
        },
        config={
            "callbacks": [langfuse_handler],
            "metadata": {
                "app": "petshop-chatbot",
                "prompt_version": langfuse_prompt.version
            },
            "tags": ["rag", "petshop"]
        }
    )

    return {
        "response": response["answer"]
    }


@app.get("/webhook")
async def verify(request: Request):
    if request.query_params.get("hub.verify_token") == "test_petshop":
        return request.query_params.get("hub.challenge")
    return "Error"

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    print(data)
    return {"status": "ok"}