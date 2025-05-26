"""
Main application entry point for the Itinerary Generator.
"""

import os
from google.adk import AgentApp
from dotenv import load_dotenv

# Load agents
from src.agents.user_agent import UserInteractionAgent
from src.agents.research_agent import ResearchAgent
from src.agents.scheduling_agent import SchedulingAgent
from src.agents.content_agent import ContentGeneratorAgent
from src.agents.coordinator_agent import CoordinatorAgent

# Load configuration
from src.config import initialize_services

def create_app():
    """Create and configure the agent application."""
    
    # Initialize services
    services = initialize_services()
    
    # Create specialized agents
    user_agent = UserInteractionAgent(services["text_model"])
    research_agent = ResearchAgent(services["text_model"], services["gmaps"])
    scheduling_agent = SchedulingAgent(services["text_model"], services["gmaps"])
    content_agent = ContentGeneratorAgent(services["text_model"])
    
    # Create coordinator agent
    coordinator = CoordinatorAgent(
        user_agent=user_agent,
        research_agent=research_agent,
        scheduling_agent=scheduling_agent,
        content_agent=content_agent
    )
    
    # Create the application with the coordinator agent
    app = AgentApp(coordinator)
    
    return app

def main():
    """Run the application."""
    
    # Load environment variables
    load_dotenv()
    
    # Create the app
    app = create_app()
    
    # Run the app
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()