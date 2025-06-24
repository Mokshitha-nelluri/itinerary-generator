"""
Research Agent to discover and evaluate attractions and activities.
"""

import os
from google.adk import Agent
from google.adk.agents import invocation_context
from tools.attraction_tools import create_attraction_search_tool, create_restaurant_search_tool, create_lodging_search_tool

class ResearchAgent(Agent):
    """Agent to research attractions and activities for the itinerary."""
    
    def __init__(self, text_model, gmaps_client):
        """
        Initialize the research agent.
        
        Args:
            text_model: Model name string (e.g., "gemini-1.5-pro") OR GenerativeModel object
            gmaps_client: Google Maps API client
        """
        # Extract model name if it's a GenerativeModel object
        if hasattr(text_model, 'model_name'):
            model_name = text_model.model_name
        elif isinstance(text_model, str):
            model_name = text_model
        else:
            model_name = "gemini-1.5-pro"  # fallback
        
        super().__init__(
            name="research_agent",
            description="Researches attractions and activities for the itinerary",
            model=text_model  # Pass the model to the parent constructor
        )
        
        # Store the maps client
        self._gmaps_client = gmaps_client
        
        # Initialize tools
        try:
            object.__setattr__(self, "attraction_tool", create_attraction_search_tool(gmaps_client))
            object.__setattr__(self, "restaurant_tool", create_restaurant_search_tool(gmaps_client))
            object.__setattr__(self, "lodging_tool", create_lodging_search_tool(gmaps_client))
        except Exception as e:
            print(f"Warning: Could not initialize research tools: {e}")
            object.__setattr__(self, "attraction_tool", None)
            object.__setattr__(self, "restaurant_tool", None)
            object.__setattr__(self, "lodging_tool", None)

    async def process(self, context: invocation_context):
        """
        Research attractions and activities based on user preferences.
        
        Args:
            context: Agent context with user preferences
            
        Returns:
            Status message after completing research
        """
        try:
            # Check if tools are available
            if not self.attraction_tool or not self.restaurant_tool:
                return "Error: Research tools are not properly initialized. Please check your Google Maps API configuration."
            
            # Get user preferences from shared memory
            preferences = context.shared_memory.get("user_preferences")
            
            if not preferences:
                return "Error: No user preferences found. Please provide your travel preferences first."
            
            destination = preferences.get("destination")
            interests = preferences.get("interests", [])
            budget = preferences.get("budget", "moderate")
            
            if not destination:
                return "Error: No destination specified in user preferences."
            
            # Research attractions based on interests
            all_attractions = []
            
            # For each interest, search for relevant attractions
            for interest in interests:
                try:
                    # Map user interests to search keywords and types
                    search_params = self._map_interest_to_search_params(interest)
                    
                    # Search for attractions - Fixed method call
                    attractions = await self.attraction_tool.execute(
                        destination, 
                        keywords=search_params["keywords"],
                        type_filter=search_params["type"]
                    )
                    
                    if isinstance(attractions, list):
                        # Add the interest category to each attraction
                        for attraction in attractions:
                            attraction["interest_category"] = interest
                        all_attractions.extend(attractions)
                        
                except Exception as e:
                    print(f"Error searching for {interest} attractions: {e}")
                    continue
                    
            # Research restaurants based on budget
            try:
                price_level = self._map_budget_to_price_level(budget)
                restaurants = await self.restaurant_tool.execute(
                    destination,
                    price_level=price_level
                )
                
                if isinstance(restaurants, list):
                    # Mark these as restaurants
                    for restaurant in restaurants:
                        restaurant["interest_category"] = "dining"
                    all_attractions.extend(restaurants)
                    
            except Exception as e:
                print(f"Error searching for restaurants: {e}")
            
            # Lodging suggestion (optional)
            if preferences.get("needs_lodging_suggestions"):
                try:
                    if not self.lodging_tool:
                        print("Lodging tool not available.")
                    else:
                        lodging_results = await self.lodging_tool.execute(
                            destination=destination,
                            radius=3000
                        )

                        if isinstance(lodging_results, list) and lodging_results:
                            # Store best lodging info
                            top_lodging = sorted(lodging_results, key=lambda x: x.get("rating", 0), reverse=True)[0]
                            context.shared_memory.set("lodging_suggestions", lodging_results)
                            context.shared_memory.set("accommodation_location", top_lodging["geometry"]["location"])
                        else:
                            print("No lodging results found.")
                except Exception as e:
                    print(f"Error searching for lodging: {e}")

            # Store research results in shared memory
            context.shared_memory.set("research_results", all_attractions)
            
            # Create a summary of findings
            summary = self._create_research_summary(all_attractions)
            
            return f"Research completed! I've found {len(all_attractions)} places of interest in {destination}.\n\n{summary}"
            
        except Exception as e:
            error_msg = f"An error occurred during research: {str(e)}"
            print(f"ResearchAgent error: {error_msg}")
            return error_msg
    
    def _map_interest_to_search_params(self, interest):
        """
        Map user interest to search parameters.
        
        Args:
            interest: User interest (e.g., "food", "culture")
            
        Returns:
            Dictionary with keywords and place type
        """
        interest_mapping = {
            "food": {
                "keywords": "food tour local cuisine",
                "type": "tourist_attraction"
            },
            "dining": {
                "keywords": "restaurant",
                "type": "restaurant"
            },
            "culture": {
                "keywords": "cultural attraction heritage",
                "type": "museum"
            },
            "history": {
                "keywords": "historical site monument",
                "type": "museum"
            },
            "art": {
                "keywords": "art gallery museum",
                "type": "museum"
            },
            "nature": {
                "keywords": "nature park garden",
                "type": "park"
            },
            "outdoor": {
                "keywords": "outdoor activities park",
                "type": "park"
            },
            "shopping": {
                "keywords": "shopping market",
                "type": "shopping_mall"
            },
            "adventure": {
                "keywords": "adventure activity tour",
                "type": "tourist_attraction"
            },
            "relaxation": {
                "keywords": "spa wellness relaxation",
                "type": "spa"
            },
            "nightlife": {
                "keywords": "nightlife entertainment",
                "type": "night_club"
            },
            "entertainment": {
                "keywords": "entertainment show theater",
                "type": "tourist_attraction"
            }
        }
        
        # Default values
        default_params = {
            "keywords": f"{interest} attraction",
            "type": "tourist_attraction"
        }
        
        return interest_mapping.get(interest.lower(), default_params)
    
    def _map_budget_to_price_level(self, budget):
        """
        Map budget level to Google Maps price level.
        
        Args:
            budget: Budget level ("budget", "moderate", "luxury")
            
        Returns:
            Price level (1-4) or None
        """
        budget_mapping = {
            "budget": 1,
            "low": 1,
            "moderate": 2,
            "medium": 2,
            "high": 3,
            "luxury": 4,
            "premium": 4
        }
        
        return budget_mapping.get(budget.lower(), 2)  # Default to moderate
    
    def _create_research_summary(self, attractions):
        """
        Create a summary of research findings.
        
        Args:
            attractions: List of attractions found
            
        Returns:
            Summary text
        """
        if not attractions:
            return "No attractions found. This might be due to API limitations or the destination name not being recognized."
        
        # Group by interest category
        categories = {}
        for attraction in attractions:
            category = attraction.get("interest_category", "general")
            if category not in categories:
                categories[category] = []
            categories[category].append(attraction)
        
        # Create summary
        summary = "Here's a summary of what I found:\n\n"
        
        for category, items in categories.items():
            summary += f"**{category.title()}**: Found {len(items)} places"
            
            # Show up to 3 top-rated places
            top_items = sorted(items, key=lambda x: x.get("rating", 0), reverse=True)[:3]
            if top_items:
                summary += " including:\n"
                for item in top_items:
                    name = item.get('name', 'Unnamed')
                    rating = item.get('rating')
                    rating_text = f" (★{rating})" if rating else ""
                    summary += f"  • {name}{rating_text}\n"
            else:
                summary += "\n"
                
            summary += "\n"
        
        return summary