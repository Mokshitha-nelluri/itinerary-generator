"""
User Interaction Agent to handle user requests and preference extraction.
"""

from google.adk import Agent, AgentContext
import json
import re

class UserInteractionAgent(Agent):
    """Agent to handle user communication and preference extraction."""
    
    def __init__(self, text_model):
        """
        Initialize the user interaction agent.
        
        Args:
            text_model: Vertex AI text generation model
        """
        super().__init__(
            name="user_interaction_agent",
            description="Extracts travel preferences from user requests"
        )
        self.text_model = text_model
    
    async def process(self, context: AgentContext):
        """
        Process the user input and extract travel preferences.
        
        Args:
            context: Agent context containing user input
            
        Returns:
            Response acknowledging the extracted preferences
        """
        user_input = context.input_message.content
        
        # Extract preferences using the LLM
        preferences = await self._extract_preferences(user_input)
        
        # Store preferences in shared context
        context.shared_memory.set("user_preferences", preferences)
        
        # Create a formatted response summarizing the preferences
        response = (
            f"I've understood your travel preferences:\n\n"
            f"📍 Destination: {preferences['destination']}\n"
            f"📅 Duration: {preferences['duration']} days\n"
            f"🎯 Interests: {', '.join(preferences['interests'])}\n"
            f"💰 Budget: {preferences['budget']}\n"
            f"🗓️ Travel dates: {preferences['start_date']} to {preferences['end_date']}\n\n"
            f"I'll create an itinerary based on these preferences."
        )
        
        return response
    
    async def _extract_preferences(self, user_input):
        """
        Extract travel preferences from user input using the LLM.
        
        Args:
            user_input: Text input from the user
            
        Returns:
            Dictionary of extracted preferences
        """
        prompt = f"""
        Extract travel preferences from the following user input:
        
        ---
        {user_input}
        ---
        
        Extract and provide the following information in JSON format:
        1. destination: The main location/city for the trip
        2. duration: Number of days for the trip (numeric value only)
        3. interests: Array of interests/themes (e.g., ["food", "culture", "history"])
        4. budget: Budget level ("budget", "moderate", "luxury")
        5. start_date: Start date in YYYY-MM-DD format (use today's date + 7 days if not specified)
        6. end_date: End date in YYYY-MM-DD format (calculate based on duration if not specified)
        
        For any information not explicitly provided, make a reasonable assumption based on the input.
        
        Respond ONLY with the JSON object, no additional text.
        """
        
        # Get response from LLM
        response = self.text_model.predict(
            prompt,
            temperature=0.2,
            max_output_tokens=512
        ).text
        
        # Extract JSON from response (in case the model includes other text)
        json_match = re.search(r'({.*})', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_str = response
            
        try:
            # Clean the JSON string to ensure it's valid
            json_str = json_str.replace('\n', ' ').replace('\t', ' ')
            preferences = json.loads(json_str)
            
            # Ensure all required fields exist
            required_fields = ['destination', 'duration', 'interests', 'budget', 'start_date', 'end_date']
            for field in required_fields:
                if field not in preferences:
                    if field == 'interests':
                        preferences[field] = ["sightseeing"]
                    elif field == 'budget':
                        preferences[field] = "moderate"
                    elif field in ['start_date', 'end_date']:
                        import datetime
                        today = datetime.datetime.now()
                        preferences['start_date'] = (today + datetime.timedelta(days=7)).strftime('%Y-%m-%d')
                        preferences['end_date'] = (today + datetime.timedelta(days=7 + int(preferences.get('duration', 3)))).strftime('%Y-%m-%d')
                    else:
                        preferences[field] = "Not specified"
                        
            return preferences
            
        except json.JSONDecodeError:
            # Fallback with default values if JSON parsing fails
            import datetime
            today = datetime.datetime.now()
            return {
                'destination': self._extract_destination(user_input),
                'duration': self._extract_duration(user_input),
                'interests': ["sightseeing"],
                'budget': "moderate",
                'start_date': (today + datetime.timedelta(days=7)).strftime('%Y-%m-%d'),
                'end_date': (today + datetime.timedelta(days=10)).strftime('%Y-%m-%d')
            }
    
    def _extract_destination(self, text):
        """Simple fallback extraction for destination."""
        common_cities = ["new york", "san francisco", "paris", "london", "tokyo", "singapore", 
                      "barcelona", "sydney", "rome", "dubai", "los angeles", "berlin"]
        
        text_lower = text.lower()
        for city in common_cities:
            if city in text_lower:
                return city.title()
        
        return "Not specified"
    
    def _extract_duration(self, text):
        """Simple fallback extraction for duration."""
        duration_patterns = [
            r'(\d+)\s*days?',
            r'(\d+)-days?',
            r'for\s*(\d+)\s*days?'
        ]
        
        for pattern in duration_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return int(match.group(1))
        
        return 3  # Default duration