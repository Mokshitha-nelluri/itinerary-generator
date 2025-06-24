"""
Content Generator Agent to create the final itinerary with descriptions.
"""

from google.adk import Agent
from google.adk.agents import invocation_context
import json

class ContentGeneratorAgent(Agent):
    """Agent to create the final itinerary with descriptions."""
    
    def __init__(self, text_model):
        """
        Initialize the content generator agent.
        
        Args:
            text_model: Model name string (e.g., "gemini-1.5-pro")
        """
        super().__init__(
            name="content_generator_agent",
            description="Creates the final itinerary with descriptions"
        )
        # Store the model name and instructions as instance variables
        object.__setattr__(self, "_text_model", text_model)
        object.__setattr__(self, "_instructions", """
            You are a travel content specialist. Your role is to:
            1. Compile research and schedule data into comprehensive itineraries
            2. Format content in an attractive, easy-to-read manner
            3. Include practical details like addresses, hours, and tips
            4. Create engaging descriptions that inspire travelers
            """)


    
    async def process(self, context: invocation_context):
        """
        Generate the final itinerary content.
        
        Args:
            context: Agent context with optimized schedule
            
        Returns:
            The generated itinerary
        """
        try:
            # Get user preferences and optimized schedule from shared memory
            preferences = context.shared_memory.get("user_preferences")
            schedule = context.shared_memory.get("optimized_schedule")
            
            if not preferences or not schedule:
                return "Error: Missing user preferences or optimized schedule. Please complete those steps first."
            
            # Generate the itinerary content
            itinerary = await self._generate_itinerary(preferences, schedule)
            
            # Store the final itinerary in shared memory
            context.shared_memory.set("final_itinerary", itinerary)
            
            return itinerary
            
        except Exception as e:
            return f"Error generating itinerary content: {str(e)}"
    
    async def _generate_itinerary(self, preferences, schedule):
        """
        Generate the complete itinerary content.
        
        Args:
            preferences: User preferences
            schedule: Optimized schedule
            
        Returns:
            The formatted itinerary
        """
        destination = preferences.get("destination", "your destination")
        duration = preferences.get("duration", "your trip")
        interests = ", ".join(preferences.get("interests", ["travel"]))
        
        # Create the itinerary header
        itinerary = f"# {duration}-Day Itinerary for {destination}\n\n"
        
        # Add introduction
        itinerary += f"""## Introduction

This personalized itinerary has been created for your {duration}-day trip to {destination}, focusing on {interests}. 
Each day has been carefully planned to give you the best experience based on your preferences and interests.

"""
        
        # Add itinerary details
        itinerary += "## Daily Schedule\n\n"
        
        for day_index, day in enumerate(schedule):
            date = day.get("date", f"Day {day_index + 1}")
            day_name = day.get("day", "")
            
            itinerary += f"### {date} ({day_name})\n\n"
            
            activities = day.get("activities", [])
            if activities:
                for activity_index, activity in enumerate(activities):
                    start_time = activity.get("start_time", "")
                    attraction = activity.get("attraction", {})
                    name = attraction.get("name", "Activity")
                    address = attraction.get("address", "")
                    
                    # Generate description for each attraction
                    description = await self._generate_attraction_description(attraction)
                    
                    itinerary += f"#### {start_time} - {name}\n\n"
                    itinerary += f"{description}\n\n"
                    
                    if address:
                        itinerary += f"**Address:** {address}\n\n"
                    
                    # Add separator between activities (except for the last one)
                    if activity_index < len(activities) - 1:
                        itinerary += "---\n\n"
            else:
                itinerary += "No activities scheduled for this day. Free day to explore on your own!\n\n"
            
            # Add day separator (except for the last day)
            if day_index < len(schedule) - 1:
                itinerary += "---\n\n"
        
        # Add travel tips
        itinerary += await self._generate_travel_tips(preferences, destination)
        
        return itinerary
    
    async def _generate_attraction_description(self, attraction):
        """
        Generate a description for an attraction.
        
        Args:
            attraction: Attraction information
            
        Returns:
            Description text
        """
        try:
            name = attraction.get("name", "this place")
            rating = attraction.get("rating", "")
            category = attraction.get("interest_category", "")
            
            # Create prompt for the description
            prompt = f"""
            Write a brief, engaging description (2-3 sentences) for a travel itinerary about the following attraction:
            
            Name: {name}
            Category: {category}
            Rating: {rating}
            
            The description should be informative and enticing, highlighting what makes this place special.
            Do not mention the rating explicitly in your description.
            Write in second person, addressing the traveler directly.
            """
            
            # FIXED: Use the agent's model properly through the SDK
            response = await self.generate(
                prompt,
                temperature=0.7,
                max_tokens=256
            )
            
            return response.strip()
            
        except Exception as e:
            # Fallback description if generation fails
            name = attraction.get("name", "this attraction")
            return f"Visit {name}, a wonderful destination that's sure to enhance your travel experience."
    
    async def _generate_travel_tips(self, preferences, destination):
        """
        Generate travel tips for the destination.
        
        Args:
            preferences: User preferences
            destination: Travel destination
            
        Returns:
            Travel tips text
        """
        try:
            budget = preferences.get("budget", "moderate")
            interests = ", ".join(preferences.get("interests", ["travel"]))
            
            # Create prompt for travel tips
            prompt = f"""
            Write a brief section of travel tips for a trip to {destination} with a {budget} budget, focusing on {interests}.
            
            Include:
            1. A tip about local transportation
            2. A tip about local customs or etiquette
            3. A money-saving tip relevant to the budget level
            4. A tip related to the main interests
            
            Format each tip with a bullet point. Keep each tip concise (1-2 sentences).
            Write in second person, addressing the traveler directly.
            """
            
            # FIXED: Use the agent's model properly through the SDK
            response = await self.generate(
                prompt,
                temperature=0.7,
                max_tokens=512
            )
            
            return f"\n## Travel Tips\n\n{response.strip()}\n"
            
        except Exception as e:
            # Fallback tips if generation fails
            return f"\n## Travel Tips\n\n• Research local transportation options before you arrive\n• Respect local customs and dress codes\n• Look for local markets and street food for budget-friendly meals\n• Check opening hours and book popular attractions in advance\n"