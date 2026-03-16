from fastapi import FastAPI
from pydantic import BaseModel

from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import CharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate


from langchain_classic.chains import create_retrieval_chain
from langchain_classic.chains.combine_documents import create_stuff_documents_chain

# -------------------------
# Load Knowledge Base
# -------------------------

loader = TextLoader("petshop_data.txt")
documents = loader.load()

splitter = CharacterTextSplitter(chunk_size=500, chunk_overlap=50)
docs = splitter.split_documents(documents)

# -------------------------
# Embeddings + Vector DB
# -------------------------

embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

vectorstore = FAISS.from_documents(docs, embeddings)

retriever = vectorstore.as_retriever()

# -------------------------
# LLM
# -------------------------

llm = ChatOpenAI(
    temperature=0.3,
    model="gpt-4o-mini"
)

# -------------------------
# Prompt
# -------------------------

prompt = ChatPromptTemplate.from_template(
"""
You are a helpful Tunisian pet shop assistant.

Answer in Tunisian dialect (Derja).
Be short and friendly.

Context:
{context}

Customer question:
{input}
"""
)

# -------------------------
# RAG Chain
# -------------------------

document_chain = create_stuff_documents_chain(llm, prompt)

qa_chain = create_retrieval_chain(retriever, document_chain)

# -------------------------
# FastAPI
# -------------------------

app = FastAPI()

class ChatRequest(BaseModel):
    message: str


@app.post("/chat")
def chat(req: ChatRequest):

    response = qa_chain.invoke({
        "input": req.message
    })

    return {"response": response["answer"]}