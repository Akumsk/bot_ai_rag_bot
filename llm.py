import os
import pandas as pd
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.document_loaders import PyMuPDFLoader
from langchain.text_splitter import CharacterTextSplitter
from langchain.chains import RetrievalQA
from langchain.schema import Document  # Import the correct Document schema from LangChain
from docx import Document as Doc  # For Word documents
from io import StringIO

# Set up OpenAI API key
openai_api_key = os.getenv('OPENAI_API_KEY')

# Initialize LLM
llm = ChatOpenAI(openai_api_key=openai_api_key, model_name='gpt-4o')

vector_store = None

def load_excel_file(file_path):
    """Load content from an Excel file as text."""
    data = pd.read_excel(file_path)
    text_data = StringIO()
    data.to_string(buf=text_data)
    return text_data.getvalue()

def load_word_file(file_path):
    """Load content from a Word file (.docx)."""
    doc = Doc(file_path)
    return "\n".join([para.text for para in doc.paragraphs])

# Updated function to load and process PDF, Word, and Excel files and create FAISS index
def load_and_index_documents(folder_path):
    global vector_store

    # Load and read documents (PDF, Word, Excel) from folder and subfolders
    documents = []
    found_valid_file = False  # Track whether any valid documents are found

    # Walk through the folder and its subfolders
    for dirpath, _, filenames in os.walk(folder_path):
        for filename in filenames:
            file_path = os.path.join(dirpath, filename)

            # Handle PDF files
            if filename.endswith(".pdf"):
                loader = PyMuPDFLoader(file_path)
                docs = loader.load()
                for doc in docs:
                    doc.metadata = {"source": filename}  # Attach the filename to the document metadata
                    documents.append(doc)  # Add each PDF page as a document object
                found_valid_file = True  # Mark that we found a valid file

            # Handle Word files
            elif filename.endswith(".docx"):
                content = load_word_file(file_path)
                doc = Document(page_content=content, metadata={"source": filename})  # Use Langchain's Document schema
                documents.append(doc)
                found_valid_file = True  # Mark that we found a valid file

            # Handle Excel files
            elif filename.endswith(".xlsx"):
                content = load_excel_file(file_path)
                doc = Document(page_content=content, metadata={"source": filename})  # Use Langchain's Document schema
                documents.append(doc)
                found_valid_file = True  # Mark that we found a valid file

    # If no valid files were found, provide an appropriate error message
    if not found_valid_file:
        return "No valid files found in the folder or subfolders. Please provide PDF, Word, or Excel files."

    # Split documents into smaller chunks
    text_splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    split_docs = text_splitter.split_documents(documents)

    # Create embeddings using OpenAI embeddings
    embeddings = OpenAIEmbeddings(openai_api_key=openai_api_key)

    # Use FAISS from Langchain to store the document embeddings
    vector_store = FAISS.from_documents(split_docs, embeddings)
    return "Documents successfully indexed."

# Function to handle retrieving and generating response using RAG
def retrieve_and_generate(prompt: str):
    global vector_store
    if not vector_store:
        return "Please set the folder path using /path_folder and ensure documents are loaded.", None

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