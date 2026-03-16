import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

# Langchain
from langchain_community.document_loaders import TextLoader
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

import os
from dotenv import load_dotenv

# -------------------------
# Langfuse Initialization
# -------------------------
load_dotenv()
langfuse = Langfuse(
    public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
    secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
    host=os.getenv("LANGFUSE_BASE_URL")
)

langfuse_handler = CallbackHandler()


# -------------------------
# Load Knowledge Base
# -------------------------

loader = TextLoader("petshop_data.txt")
documents = loader.load()
print("Docs :", documents)

splitter = RecursiveCharacterTextSplitter(
    chunk_size=350,
    chunk_overlap=40
)

docs = splitter.split_documents(documents)


# -------------------------
# Embeddings + Vector DB
# -------------------------

embeddings = HuggingFaceEmbeddings(
    model_name="BAAI/bge-small-en-v1.5"
)

vectorstore = FAISS.from_documents(docs, embeddings)

# retriever = vectorstore.as_retriever(    search_type="similarity",
#     search_kwargs={"k": 3})

retriever = vectorstore.as_retriever(
    search_type="mmr",
    search_kwargs={
        "k": 4,
        "fetch_k": 10
    }
)

print("retrieve: ", retriever)

# -------------------------
# LLM
# -------------------------

llm = ChatOpenAI(
    temperature=0,
    model="gpt-4o-mini"
)


# -------------------------
# Prompt (Loaded from Langfuse)
# -------------------------

langfuse_prompt = langfuse.get_prompt("petshop-chatbot-prompt")

prompt = ChatPromptTemplate.from_template(
    langfuse_prompt.prompt
)


# -------------------------
# RAG Chain
# -------------------------

document_chain = create_stuff_documents_chain(
    llm,
    prompt
)


qa_chain = create_retrieval_chain(
    retriever,
    document_chain
)


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


@app.post("/chat")
def chat(req: ChatRequest):

    response = qa_chain.invoke(
        {
            "input": req.message
        },
        config={
            "callbacks": [langfuse_handler],
            "metadata": {
                "app": "petshop-chatbot"
            },
            "tags": ["rag", "petshop"]
        }
    )

    return {
        "response": response["answer"]
    }