"""
Scheduling Agent to optimize the timing and logistics of the itinerary.
"""

from google.adk import Agent
from google.adk.agents import invocation_context
from tools import scheduling_tools
from datetime import datetime, timedelta

class SchedulingAgent(Agent):
    """Agent to optimize the timing and logistics of the itinerary."""

    def __init__(self, text_model, gmaps_client, gemini_api_key=None):
        """
        Initialize the scheduling agent.

        Args:
            text_model: Model name string (e.g., "gemini-1.5-pro") OR GenerativeModel object
            gmaps_client: Google Maps API client
            gemini_api_key: Optional Gemini API key for enhanced recommendations
        """
        instructions = """
        You are a travel scheduling specialist. Your role is to:
        1. Create logical daily schedules based on research findings
        2. Optimize routes to minimize travel time
        3. Consider opening hours and practical constraints
        4. Balance activities throughout the trip duration
        5. Ensure efficient use of time while allowing for rest and meals
        """

        super().__init__(
            name="scheduling_agent",
            description="Optimizes the timing and logistics of the itinerary",
            model=text_model,
            instruction=instructions
        )

        # Set up shared clients in the tool module
        scheduling_tools.setup_clients(gmaps_client, gemini_api_key)

        # Store function reference for scheduling
        self._schedule_optimizer = scheduling_tools.optimize_schedule

    async def process(self, context: invocation_context):
        """
        Create an optimized schedule based on research results.

        Args:
            context: Agent context with research results

        Returns:
            Status message after completing scheduling
        """
        try:
            preferences = context.shared_memory.get("user_preferences")
            attractions = context.shared_memory.get("research_results")

            if not preferences or not attractions:
                return "Error: Missing user preferences or research results. Please complete those steps first."

            start_date = preferences.get("start_date")
            duration = preferences.get("duration")
            end_date = preferences.get("end_date")

            if not end_date and start_date and duration:
                start = datetime.strptime(start_date, "%Y-%m-%d")
                end_date = (start + timedelta(days=int(duration) - 1)).strftime("%Y-%m-%d")

            accommodation_location = context.shared_memory.get("accommodation_location")
            if not accommodation_location:
                accommodation_location = preferences.get("accommodation_location")

            start_time = preferences.get("start_time", "9:00")
            end_time = preferences.get("end_time", "21:00")
            return_to_accommodation = preferences.get("return_to_accommodation", True)

            # Call the global coroutine directly
            schedule = await self._schedule_optimizer(
                attractions=attractions,
                start_date=start_date,
                end_date=end_date,
                accommodation_location=accommodation_location,
                start_time=start_time,
                end_time=end_time,
                return_to_accommodation=return_to_accommodation
            )

            context.shared_memory.set("optimized_schedule", schedule)
            summary = self._create_schedule_summary(schedule)

            return f"Scheduling completed! I've created an optimized itinerary across {len(schedule) if schedule else 0} days.\n\n{summary}"

        except Exception as e:
            return f"Error creating schedule: {str(e)}"

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
                    summary += f"- {start_time}: {name} ({duration})\n" if duration else f"- {start_time}: {name}\n"
            else:
                note = day.get("note", "No activities scheduled")
                summary += f"- {note}\n"

            if day.get("return_to_accommodation"):
                return_info = day["return_to_accommodation"]
                departure = return_info.get("departure_time", "")
                arrival = return_info.get("arrival_time", "")
                if departure and arrival:
                    summary += f"- {departure}: Return to accommodation (arrive {arrival})\n"
                elif departure:
                    summary += f"- {departure}: Return to accommodation\n"

            summary += "\n"

        return summary
