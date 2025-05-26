import os #functions for interacting with the operating system (eg: reading env var)
from dotenv import load_dotenv #loads env vars from .env file
import vertexai #SDK for interacting with google cloud's vertexai
from vertexai.language_models import TextGenerationModel #class from vertxai for running text generation models
import googlemaps #google maps client

load_dotenv()

#read and access configurations from .env
PROJECT_ID = os.getenv("PROJECT_ID")
LOCATION = os.getenv("LOCATION", "us-central1")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

#LLM settings
MODEL_NAME = os.getenv("MODEL_NAME", "text-bison@002") # Fetch value from .env. If doesnt exist fallback to using text-bison@002
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.2")) #c ontrols randomness. It adjusts the confidence of the model's next word choices. Modifies the prob distribution before a token is chosen.
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "1024")) #limits the length of model's response

def initialize_services():
    """Initialize and return all required Google Cloud services."""
    
    # Initialize Vertex AI
    vertexai.init(project=PROJECT_ID, location=LOCATION)
    
    # Initialize the text generation model
    text_model = TextGenerationModel.from_pretrained(MODEL_NAME)
    
    # Initialize Google Maps client
    gmaps = googlemaps.Client(key=GOOGLE_MAPS_API_KEY)
    
    return {
        "text_model": text_model,
        "gmaps": gmaps
    }

def get_generation_config():
    """Return standard generation config for text models."""
    return {
        "temperature": TEMPERATURE,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "top_p": 0.95, #Implements nucleas sampling 
        "top_k": 40 #only consider the top k most likely tokens
    }

### Notes:
# Nucleus sampling: is a probabilistic decoding strategy used when generating text. It controls how the model selects the next word/token during generation.
# Instead of always picking the most likely word (which would be deterministic and repetitive), nucleus sampling introduces randomness, but in a smart, controlled way.
# For each next token, the model gives a probability distribution: a list of all possible tokens and their likelihoods.
# The model ranks them from most to least likely.
# Starting from the top, it adds up probabilities until the total reaches or exceeds top_p.
# Now the model randomly picks one token from this shortlist based on their probabilities.
###

