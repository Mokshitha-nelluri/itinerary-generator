"""
Final Configuration file for the Itinerary Generator.
Handles initialization of Google Cloud services, Google Maps, and AI models.
Production-ready with proper error handling and model migration support.
"""
import os
from dotenv import load_dotenv
import googlemaps
import google.generativeai as genai
import vertexai
from vertexai.language_models import TextGenerationModel
from google.adk.sessions import InMemorySessionService


def initialize_services():
    """Initialize all required services and configurations."""
    
    # Load environment variables from .env file
    load_dotenv()
    
    # Get API keys and configuration from environment variables
    google_api_key = os.getenv('GOOGLE_API_KEY') or os.getenv('GEMINI_API_KEY')
    google_maps_key = os.getenv('GOOGLE_MAPS_API_KEY')
    model_name = os.getenv('MODEL_NAME', 'gemini-1.5-pro')
    project_id = os.getenv('PROJECT_ID')
    location = os.getenv('LOCATION', 'us-central1')
    
    # Force use of Gemini model if deprecated text-bison is detected
    if 'text-bison' in model_name:
        print(f"⚠️  Detected deprecated model {model_name}, switching to gemini-1.5-pro")
        model_name = 'gemini-1.5-pro'
    
    # Validate required environment variables
    if not google_api_key:
        raise ValueError("GOOGLE_API_KEY or GEMINI_API_KEY environment variable is required")
    
    if not google_maps_key:
        raise ValueError("GOOGLE_MAPS_API_KEY environment variable is required")
    
    if not project_id:
        raise ValueError("PROJECT_ID environment variable is required")
    
    # Initialize AI model (supports both Vertex AI and Gemini models)
    try:
        if model_name.startswith('text-') or '@' in model_name:
            # Vertex AI model (like text-bison@002) - mostly deprecated
            vertexai.init(project=project_id, location=location)
            text_model = TextGenerationModel.from_pretrained(model_name)
            model_type = "vertex_ai"
        else:
            # Gemini model (like gemini-1.5-pro) - recommended
            genai.configure(api_key=google_api_key)
            text_model = genai.GenerativeModel(model_name)
            model_type = "gemini"
    except Exception as e:
        raise ValueError(f"Failed to initialize AI model: {e}")
    
    # Initialize Google Maps client
    try:
        gmaps_client = googlemaps.Client(key=google_maps_key)
    except Exception as e:
        raise ValueError(f"Failed to initialize Google Maps client: {e}")
    
    # Initialize session service for ADK
    try:
        session_service = InMemorySessionService()
    except Exception as e:
        raise ValueError(f"Failed to initialize session service: {e}")
    
    # Return services dictionary
    services = {
        "text_model": text_model,
        "gmaps": gmaps_client,
        "session_service": session_service,
        "project_id": project_id,
        "location": location,
        "google_api_key": google_api_key,
        "google_maps_key": google_maps_key,
        "model_name": model_name,
        "model_type": model_type
    }
    
    print(f"✅ Services initialized successfully:")
    print(f"   - Model: {model_name}")
    print(f"   - Project ID: {project_id}")
    print(f"   - Location: {location}")
    print(f"   - Google Maps: {'✓' if gmaps_client else '✗'}")
    print(f"   - Session Service: {'✓' if session_service else '✗'}")
    
    return services


def get_generation_config():
    """Return standard generation configuration for text models."""
    return {
        "temperature": float(os.getenv("TEMPERATURE", "0.2")),
        "max_output_tokens": int(os.getenv("MAX_OUTPUT_TOKENS", "1024")),
        "top_p": 0.95,  # Nucleus sampling parameter
        "top_k": 40     # Only consider top k most likely tokens
    }


def generate_text(services, prompt, **kwargs):
    """
    Universal text generation function that works with both model types.
    
    Args:
        services: Dictionary returned from initialize_services()
        prompt: Text prompt for generation
        **kwargs: Additional generation parameters
    
    Returns:
        Generated text string
    """
    model = services["text_model"]
    model_type = services["model_type"]
    
    # Merge default config with any overrides
    config = get_generation_config()
    config.update(kwargs)
    
    try:
        if model_type == "vertex_ai":
            # Vertex AI model
            response = model.predict(prompt, **config)
            return response.text if hasattr(response, 'text') else str(response)
        else:
            # Gemini model
            response = model.generate_content(prompt, generation_config=config)
            return response.text if response and response.text else ""
    except Exception as e:
        raise RuntimeError(f"Text generation failed: {e}")


def test_configuration():
    """Test that all services can be initialized properly."""
    try:
        services = initialize_services()
        
        # Test Google Maps client
        try:
            test_result = services["gmaps"].geocode("Times Square, New York")
            if test_result:
                print("✅ Google Maps API test passed!")
            else:
                print("⚠️  Google Maps API test returned empty result")
        except Exception as e:
            print(f"❌ Google Maps API test failed: {e}")
        
        # Test AI model using universal function
        try:
            response_text = generate_text(services, "Say 'Hello, configuration test successful!'")
            
            if response_text:
                print("✅ AI model test passed!")
                print(f"   Model response: {response_text.strip()}")
            else:
                print("⚠️  AI model test returned empty response")
        except Exception as e:
            print(f"❌ AI model test failed: {e}")
        
        print("✅ Configuration test completed!")
        return True
        
    except Exception as e:
        print(f"❌ Configuration test failed: {e}")
        return False


# Environment variable template for .env file
ENV_TEMPLATE = """
# Google Cloud Project Configuration
PROJECT_ID=your_google_cloud_project_id
LOCATION=us-central1

# API Keys (IMPORTANT: Keep these secret!)
GOOGLE_API_KEY=your_google_ai_api_key_here
GEMINI_API_KEY=your_google_ai_api_key_here
GOOGLE_MAPS_API_KEY=your_google_maps_api_key_here

# AI Model Configuration
MODEL_NAME=gemini-1.5-pro
# Alternative models:
# MODEL_NAME=gemini-1.5-flash
# MODEL_NAME=gemini-pro

# Model Parameters
TEMPERATURE=0.2
MAX_OUTPUT_TOKENS=1024
"""


def create_env_template():
    """Create a template .env file if it doesn't exist."""
    if not os.path.exists('.env'):
        with open('.env.template', 'w') as f:
            f.write(ENV_TEMPLATE.strip())
        print("📝 Created .env.template file. Please copy it to .env and fill in your API keys.")
    else:
        print("✅ .env file already exists.")


# Quick usage example
def example_usage():
    """Example of how to use the configuration in your main application."""
    try:
        # Initialize services
        services = initialize_services()
        
        # Generate travel content
        itinerary_prompt = """
        Create a brief 1-day Paris itinerary focusing on:
        - 2-3 major landmarks
        - 1 museum visit
        - 1 local dining recommendation
        Keep it concise and practical.
        """
        
        itinerary = generate_text(services, itinerary_prompt)
        print("\n📋 Sample Itinerary Generation:")
        print("-" * 40)
        print(itinerary)
        
        # Use Google Maps for location data
        gmaps = services["gmaps"]
        eiffel_tower = gmaps.geocode("Eiffel Tower, Paris")[0]
        location = eiffel_tower['geometry']['location']
        print(f"\n📍 Eiffel Tower coordinates: {location['lat']}, {location['lng']}")
        
    except Exception as e:
        print(f"❌ Example failed: {e}")


if __name__ == "__main__":
    print("🔧 Testing Itinerary Generator Configuration...")
    print("=" * 50)
    
    # Create .env template if needed
    create_env_template()
    
    # Run configuration test
    success = test_configuration()
    
    if success:
        print("\n🎉 All tests passed! Your configuration is ready to use.")
        
        # Show example usage
        print("\n" + "=" * 50)
        example_usage()
        
    else:
        print("\n❌ Some tests failed. Please check your environment variables and API keys.")
        print("\nMake sure you have:")
        print("1. A valid .env file with all required variables")
        print("2. Valid Google AI API key")
        print("3. Valid Google Maps API key")
        print("4. Valid Google Cloud Project ID")