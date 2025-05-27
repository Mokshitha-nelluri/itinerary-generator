"""
Main application entry point for the Itinerary Generator.
"""

import os
from dotenv import load_dotenv

from google.adk import Agent
from google.adk.runners import Runner  

# Load agents
from agents.user_agent import UserInteractionAgent
from agents.research_agent import ResearchAgent
from agents.scheduling_agent import SchedulingAgent
from agents.content_agent import ContentGeneratorAgent
from agents.coordinator_agent import CoordinatorAgent

# Load configuration
from config import initialize_services

def create_agent_runtime():
    """Create and configure the agent and runtime."""
    
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
    

    # Create runtime using Runner
    runtime = Runner(app_name="itinerary_generator",
                     session_service=services["session_service"],
                     agent=coordinator)
    
    return runtime

def main():
    """Run the application (if needed standalone)."""
    load_dotenv()
    # This file only creates the runtime, but web_interface runs the server.
    # So main here can be minimal or empty if web_interface runs separately.
    pass

if __name__ == "__main__":
    main()
