"""
User Interaction Agent to handle user requests and preference extraction.
"""

from google.adk import Agent
from google.adk.agents import invocation_context
import json
import re

class UserInteractionAgent(Agent):
    """Agent to handle user communication and preference extraction."""
    
    def __init__(self, model_name):
        """
        Initialize the user interaction agent.
        
        Args:
            model_name: Model name string (e.g., "gemini-1.5-pro")
        """
        super().__init__(
            name="user_interaction_agent",
            description="Extracts travel preferences from user requests and handles user communication"
        )
        # Store the model name and instructions as instance variables
        object.__setattr__(self, "_model_name", model_name)
        object.__setattr__(self, "_instructions", """
            You are a travel preference specialist. Your role is to:
            1. Extract key travel preferences from user requests
            2. Ask clarifying questions when needed
            3. Structure preferences in a consistent format
            4. Ensure all necessary information is captured for trip planning
            5. Make reasonable assumptions when information is missing
            """)

    
    async def process(self, context: invocation_context):
        """
        Process the user input and extract travel preferences.
        
        Args:
            context: Invocation context containing user input
            
        Returns:
            Response acknowledging the extracted preferences
        """
        try:
            user_input = context.input_message.content
            
            # Extract preferences using the LLM
            preferences = await self._extract_preferences(user_input)
            
            # Validate preferences
            if not preferences.get("destination") or preferences["destination"] == "Not specified":
                return "I couldn't identify your destination. Please specify where you'd like to travel."
            
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
            
        except Exception as e:
            return f"Error processing user preferences: {str(e)}"
    
    async def _extract_preferences(self, user_input):
        """
        Extract travel preferences from user input using the LLM.
        
        Args:
            user_input: Text input from the user
            
        Returns:
            Dictionary of extracted preferences
        """
        try:
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
            
            # FIXED: Use the agent's model properly through the SDK
            response = await self.generate(
                prompt,
                temperature=0.2,
                max_tokens=512
            )
            
            # Extract JSON from response (in case the model includes other text)
            json_match = re.search(r'({.*})', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = response
                
            try:
                json_str = json_str.replace('\n', ' ').replace('\t', ' ')
                preferences = json.loads(json_str)
                
                # Ensure all required fields exist and validate
                preferences = self._validate_and_complete_preferences(preferences)
                        
                return preferences
                
            except json.JSONDecodeError:
                # Fallback with default values if JSON parsing fails
                return self._create_fallback_preferences(user_input)
                
        except Exception as e:
            # Final fallback if everything fails
            return self._create_fallback_preferences(user_input)
    
    def _validate_and_complete_preferences(self, preferences):
        """
        Validate and complete the extracted preferences.
        
        Args:
            preferences: Dictionary of preferences from LLM
            
        Returns:
            Validated and completed preferences dictionary
        """
        import datetime
        
        # Ensure all required fields exist
        required_fields = ['destination', 'duration', 'interests', 'budget', 'start_date', 'end_date']
        
        for field in required_fields:
            if field not in preferences:
                if field == 'interests':
                    preferences[field] = ["sightseeing"]
                elif field == 'budget':
                    preferences[field] = "moderate"
                elif field == 'duration':
                    preferences[field] = 3
                elif field == 'destination':
                    preferences[field] = "Not specified"
                elif field in ['start_date', 'end_date']:
                    today = datetime.datetime.now()
                    preferences['start_date'] = (today + datetime.timedelta(days=7)).strftime('%Y-%m-%d')
                    duration_days = int(preferences.get('duration', 3))
                    preferences['end_date'] = (today + datetime.timedelta(days=7 + duration_days - 1)).strftime('%Y-%m-%d')
        
        # Validate and fix data types
        try:
            preferences['duration'] = int(preferences['duration'])
        except (ValueError, TypeError):
            preferences['duration'] = 3
        
        # Ensure interests is a list
        if not isinstance(preferences['interests'], list):
            if isinstance(preferences['interests'], str):
                preferences['interests'] = [preferences['interests']]
            else:
                preferences['interests'] = ["sightseeing"]
        
        # Validate budget level
        valid_budgets = ["budget", "moderate", "luxury"]
        if preferences['budget'].lower() not in valid_budgets:
            preferences['budget'] = "moderate"
        else:
            preferences['budget'] = preferences['budget'].lower()
        
        # Validate dates
        try:
            datetime.datetime.strptime(preferences['start_date'], '%Y-%m-%d')
            datetime.datetime.strptime(preferences['end_date'], '%Y-%m-%d')
        except (ValueError, TypeError):
            today = datetime.datetime.now()
            preferences['start_date'] = (today + datetime.timedelta(days=7)).strftime('%Y-%m-%d')
            duration_days = int(preferences.get('duration', 3))
            preferences['end_date'] = (today + datetime.timedelta(days=7 + duration_days - 1)).strftime('%Y-%m-%d')
        
        return preferences
    
    def _create_fallback_preferences(self, user_input):
        """
        Create fallback preferences when LLM extraction fails.
        
        Args:
            user_input: Original user input text
            
        Returns:
            Dictionary with fallback preferences
        """
        import datetime
        
        today = datetime.datetime.now()
        duration = self._extract_duration(user_input)
        
        return {
            'destination': self._extract_destination(user_input),
            'duration': duration,
            'interests': self._extract_interests(user_input),
            'budget': "moderate",
            'start_date': (today + datetime.timedelta(days=7)).strftime('%Y-%m-%d'),
            'end_date': (today + datetime.timedelta(days=7 + duration - 1)).strftime('%Y-%m-%d')
        }
    
    def _extract_destination(self, text):
        """Simple fallback extraction for destination."""
        common_cities = [
            "new york", "san francisco", "paris", "london", "tokyo", "singapore", 
            "barcelona", "sydney", "rome", "dubai", "los angeles", "berlin",
            "amsterdam", "madrid", "vienna", "prague", "budapest", "lisbon",
            "stockholm", "copenhagen", "zurich", "milan", "florence", "venice"
        ]
        
        text_lower = text.lower()
        for city in common_cities:
            if city in text_lower:
                return city.title()
        
        # Try to find capitalized words that might be destinations
        words = re.findall(r'\b[A-Z][a-z]+\b', text)
        if words:
            return words[0]
        
        return "Not specified"
    
    def _extract_duration(self, text):
        """Simple fallback extraction for duration."""
        duration_patterns = [
            r'(\d+)\s*days?',
            r'(\d+)-days?',
            r'for\s*(\d+)\s*days?',
            r'(\d+)\s*day\s*trip',
            r'week(?:end)?',  # Special case for weekend
        ]
        
        for pattern in duration_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if pattern == r'week(?:end)?':
                    return 2  # Weekend = 2 days
                try:
                    return int(match.group(1))
                except (ValueError, IndexError):
                    continue
        
        return 3  # Default duration
    
    def _extract_interests(self, text):
        """Simple fallback extraction for interests."""
        interest_keywords = {
            'food': ['food', 'restaurant', 'cuisine', 'eating', 'dining', 'culinary'],
            'culture': ['culture', 'museum', 'art', 'gallery', 'cultural', 'heritage'],
            'history': ['history', 'historical', 'ancient', 'monument', 'castle'],
            'nature': ['nature', 'park', 'hiking', 'outdoor', 'mountain', 'beach'],
            'nightlife': ['nightlife', 'bar', 'club', 'party', 'entertainment'],
            'shopping': ['shopping', 'market', 'boutique', 'mall', 'souvenir'],
            'architecture': ['architecture', 'building', 'church', 'cathedral', 'temple']
        }
        
        text_lower = text.lower()
        found_interests = []
        
        for interest, keywords in interest_keywords.items():
            if any(keyword in text_lower for keyword in keywords):
                found_interests.append(interest)
        
        return found_interests if found_interests else ["sightseeing"]