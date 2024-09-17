import os
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.document_loaders import PyMuPDFLoader
from langchain.text_splitter import CharacterTextSplitter
from langchain.chains import RetrievalQA

# Set up OpenAI API key
openai_api_key = os.getenv('OPENAI_API_KEY')

# Initialize LLM
llm = ChatOpenAI(openai_api_key=openai_api_key, model_name='gpt-4o')

vector_store = None

# Function to load and process PDF files and create FAISS index
def load_and_index_pdfs(folder_path):
    global vector_store

    # Load and read PDFs from folder
    documents = []
    for filename in os.listdir(folder_path):
        if filename.endswith(".pdf"):
            file_path = os.path.join(folder_path, filename)
            loader = PyMuPDFLoader(file_path)
            docs = loader.load()
            for doc in docs:
                doc.metadata = {"source": filename}  # Attach the filename to the document metadata
            documents.extend(docs)

    # Split documents into smaller chunks
    text_splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    split_docs = text_splitter.split_documents(documents)

    # Create embeddings using OpenAI embeddings
    embeddings = OpenAIEmbeddings(openai_api_key=openai_api_key)

    # Use FAISS from Langchain to store the document embeddings
    vector_store = FAISS.from_documents(split_docs, embeddings)

# Function to handle retrieving and generating response using RAG
def retrieve_and_generate(prompt: str):
    global vector_store
    if not vector_store:
        return "Please set the folder path using /path_folder and ensure PDFs are loaded.", None

    # Set up retriever
    retriever = vector_store.as_retriever()

    # Use Langchain's RetrievalQA Chain to get the response
    qa_chain = RetrievalQA.from_chain_type(
        llm=llm,
        retriever=retriever,
        chain_type="stuff",
        return_source_documents=True  # Ensure that source documents are returned
    )

    try:
        # Use .invoke() method instead of deprecated __call__()
        result = qa_chain.invoke({"query": prompt})

        # Ensure 'source_documents' key is present and retrieve documents
        sources = result.get("source_documents", [])
        if not sources:
            return result["result"], None  # Return response without source if no documents were retrieved

        # Extract the filenames from the source documents
        source_files = set([doc.metadata["source"] for doc in sources if "source" in doc.metadata])

        response = result["result"]
        return response, source_files

    except KeyError as e:
        # Handle unexpected keys in the result
        return f"Error: Missing key {str(e)} in response.", None

    except Exception as e:
        # Catch any other errors
        return f"An error occurred: {str(e)}", None
