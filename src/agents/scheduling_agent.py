"""
Scheduling Agent to optimize the timing and logistics of the itinerary.
"""

from google.adk import Agent, AgentContext
from src.tools.scheduling_tools import ScheduleOptimizerTool, DistanceMatrixTool

class SchedulingAgent(Agent):
    """Agent to optimize the timing and logistics of the itinerary."""
    
    def __init__(self, text_model, gmaps_client):
        """
        Initialize the scheduling agent.
        
        Args:
            text_model: Vertex AI text generation model
            gmaps_client: Google Maps API client
        """
        super().__init__(
            name="scheduling_agent",
            description="Optimizes the timing and logistics of the itinerary"
        )
        self.text_model = text_model
        
        # Register tools
        self.schedule_optimizer = ScheduleOptimizerTool(gmaps_client)
        self.distance_matrix = DistanceMatrixTool(gmaps_client)
        self.register_tool(self.schedule_optimizer)
        self.register_tool(self.distance_matrix)
    
    async def process(self, context: AgentContext):
        """
        Create an optimized schedule based on research results.
        
        Args:
            context: Agent context with research results
            
        Returns:
            Status message after completing scheduling
        """
        # Get user preferences and research results from shared memory
        preferences = context.shared_memory.get("user_preferences")
        attractions = context.shared_memory.get("research_results")
        
        if not preferences or not attractions:
            return "Error: Missing user preferences or research results. Please complete those steps first."
        
        # Extract required information
        start_date = preferences.get("start_date")
        duration = preferences.get("duration")
        
        # Calculate end date if not already provided
        if not preferences.get("end_date") and start_date and duration:
            from datetime import datetime, timedelta
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end_date = (start + timedelta(days=int(duration) - 1)).strftime("%Y-%m-%d")
        else:
            end_date = preferences.get("end_date")
        
        # Optimize the schedule
        schedule = await self.schedule_optimizer.execute(
            attractions=attractions,
            start_date=start_date,
            end_date=end_date
        )
        
        # Store the optimized schedule in shared memory
        context.shared_memory.set("optimized_schedule", schedule)
        
        # Create a summary of the schedule
        summary = self._create_schedule_summary(schedule)
        
        return f"Scheduling completed! I've created an optimized itinerary across {len(schedule)} days.\n\n{summary}"
    
    def _create_schedule_summary(self, schedule):
        """
        Create a summary of the optimized schedule.
        
        Args:
            schedule: The optimized schedule
            
        Returns:
            Summary text
        """
        if isinstance(schedule, dict) and "error" in schedule:
            return f"Error in scheduling: {schedule['error']}"
        
        if not schedule:
            return "No schedule was created."
        
        summary = "Here's a quick overview of your itinerary:\n\n"
        
        for day_index, day in enumerate(schedule):
            date = day.get("date", f"Day {day_index + 1}")
            day_name = day.get("day", "")
            
            summary += f"**{date} ({day_name})**\n"
            
            activities = day.get("activities", [])
            if activities:
                for activity in activities:
                    start_time = activity.get("start_time", "")
                    attraction = activity.get("attraction", {})
                    name = attraction.get("name", "Activity")
                    
                    summary += f"- {start_time}: {name}\n"
            else:
                summary += "- No activities scheduled\n"
            
            summary += "\n"
        
        return summary