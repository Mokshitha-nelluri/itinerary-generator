"""
Scheduling Agent to optimize the timing and logistics of the itinerary.
"""

from google.adk import Agent
from google.adk.agents import invocation_context
from tools.scheduling_tools import create_scheduling_tools

class SchedulingAgent(Agent):
    """Agent to optimize the timing and logistics of the itinerary."""
    
    def __init__(self, text_model, gmaps_client, gemini_api_key=None):
        """
        Initialize the scheduling agent.
        
        Args:
            text_model: Vertex AI text generation model
            gmaps_client: Google Maps API client
            gemini_api_key: Optional Gemini API key for enhanced recommendations
        """
        super().__init__(
            name="scheduling_agent",
            description="Optimizes the timing and logistics of the itinerary"
        )
        object.__setattr__(self, "_text_model", text_model)
        
        # Create and register tools
        schedule_optimizer_tool, distance_matrix_tool = create_scheduling_tools(gmaps_client, gemini_api_key)
        
       
        
        
        # Store references for direct access if needed
        object.__setattr__(self, "_schedule_optimizer", schedule_optimizer_tool)
        object.__setattr__(self, "_distance_matrix", distance_matrix_tool)
        
    
    async def process(self, context: invocation_context):
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
        
        # Get additional preferences
        accommodation_location = preferences.get("accommodation_location")
        start_time = preferences.get("start_time", "9:00")
        end_time = preferences.get("end_time", "21:00")
        return_to_accommodation = preferences.get("return_to_accommodation", True)
        
        # Optimize the schedule using the tool
        schedule = await self._schedule_optimizer.execute(
            attractions=attractions,
            start_date=start_date,
            end_date=end_date,
            accommodation_location=accommodation_location,
            start_time=start_time,
            end_time=end_time,
            return_to_accommodation=return_to_accommodation
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
                    duration = activity.get("duration", "")
                    
                    summary += f"- {start_time}: {name} ({duration})\n"
            else:
                note = day.get("note", "No activities scheduled")
                summary += f"- {note}\n"
            
            # Add return to accommodation info if available
            if day.get("return_to_accommodation"):
                return_info = day["return_to_accommodation"]
                departure = return_info.get("departure_time", "")
                arrival = return_info.get("arrival_time", "")
                summary += f"- {departure}: Return to accommodation (arrive {arrival})\n"
            
            summary += "\n"
        
        return summary