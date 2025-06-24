"""
Coordinator Agent to orchestrate the workflow between all agents.
"""

import os
from google.adk import Agent
from google.adk.agents import invocation_context

class CoordinatorAgent(Agent):
    """Agent to coordinate the workflow between all specialized agents."""
    
    def __init__(self, text_model, user_agent, research_agent, scheduling_agent, content_agent):
        """
        Initialize the coordinator agent.
        
        Args:
            text_model: The model name string or GenerativeModel object
            user_agent: The user interaction agent
            research_agent: The research agent
            scheduling_agent: The scheduling agent
            content_agent: The content generator agent
        """
        
        # Extract model name if it's a GenerativeModel object
        if hasattr(text_model, 'model_name'):
            model_name = text_model.model_name
        elif isinstance(text_model, str):
            model_name = text_model
        else:
            model_name = "gemini-1.5-pro"
        
        super().__init__(
            name="coordinator_agent",
            description="Coordinates the itinerary generation workflow",
            model=text_model  # Pass the model to the parent constructor
        )
        
        object.__setattr__(self, "user_agent", user_agent)
        object.__setattr__(self, "research_agent", research_agent)
        object.__setattr__(self, "scheduling_agent", scheduling_agent)
        object.__setattr__(self, "content_agent", content_agent)

    async def process(self, context: invocation_context):
        """
        Process the user request and coordinate the itinerary generation workflow.
        
        Args:
            context: Agent context with user input
            
        Returns:
            The final itinerary
        """
        try:
            # Step 1: Extract user preferences
            await self._log_step(context, "Extracting your travel preferences...")
            user_response = await self.user_agent.process(context)
            await self._log_progress(context, "User preferences analyzed")
            
            # Step 2: Research attractions and activities
            await self._log_step(context, "Researching attractions and activities based on your preferences...")
            research_response = await self.research_agent.process(context)
            await self._log_progress(context, "Research completed")
            
            # Step 3: Create optimized schedule
            await self._log_step(context, "Creating an optimized schedule for your trip...")
            schedule_response = await self.scheduling_agent.process(context)
            await self._log_progress(context, "Schedule optimized")
            
            # Step 4: Generate final itinerary content
            await self._log_step(context, "Generating your personalized itinerary...")
            itinerary = await self.content_agent.process(context)
            
            # Final response
            await self._log_step(context, "✅ Completed! Here's your personalized itinerary:")
            
            return itinerary
            
        except Exception as e:
            error_msg = f"I encountered an error while generating your itinerary: {str(e)}"
            await self._log_step(context, f"❌ Error: {error_msg}")
            return error_msg
    
    async def _log_step(self, context, message):
        """
        Log a step in the workflow.
        
        Args:
            context: Agent context
            message: Step message
        """
        if hasattr(context, 'agent_logger'):
            context.agent_logger.info(f"[Coordinator] {message}")
        else:
            print(f"[Coordinator] {message}")
    
    async def _log_progress(self, context, message):
        """
        Log progress in the workflow.
        
        Args:
            context: Agent context
            message: Progress message
        """
        if hasattr(context, 'agent_logger'):
            context.agent_logger.info(f"[Coordinator] Progress: {message}")
        else:
            print(f"[Coordinator] Progress: {message}")