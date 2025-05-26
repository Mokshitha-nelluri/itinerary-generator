"""
Research Agent to discover and evaluate attractions and activities.
"""

from google.adk import Agent, AgentContext
from src.tools.attraction_tools import AttractionSearchTool, RestaurantSearchTool

class ResearchAgent(Agent):
    """Agent to research attractions and activities for the itinerary."""
    
    def __init__(self, text_model, gmaps_client):
        """
        Initialize the research agent.
        
        Args:
            text_model: Vertex AI text generation model
            gmaps_client: Google Maps API client
        """
        super().__init__(
            name="research_agent",
            description="Researches attractions and activities for the itinerary"
        )
        self.text_model = text_model
        
        # Register tools
        self.attraction_tool = AttractionSearchTool(gmaps_client)
        self.restaurant_tool = RestaurantSearchTool(gmaps_client)
        self.register_tool(self.attraction_tool)
        self.register_tool(self.restaurant_tool)
    
    async def process(self, context: AgentContext):
        """
        Research attractions and activities based on user preferences.
        
        Args:
            context: Agent context with user preferences
            
        Returns:
            Status message after completing research
        """
        # Get user preferences from shared memory
        preferences = context.shared_memory.get("user_preferences")
        
        if not preferences:
            return "Error: No user preferences found. Please provide your travel preferences first."
        
        destination = preferences["destination"]
        interests = preferences["interests"]
        budget = preferences["budget"]
        
        # Research attractions based on interests
        all_attractions = []
        
        # For each interest, search for relevant attractions
        for interest in interests:
            # Map user interests to search keywords and types
            search_params = self._map_interest_to_search_params(interest)
            
            # Search for attractions
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
                
        # Research restaurants based on budget
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
        
        # Store research results in shared memory
        context.shared_memory.set("research_results", all_attractions)
        
        # Create a summary of findings
        summary = self._create_research_summary(all_attractions)
        
        return f"Research completed! I've found {len(all_attractions)} places of interest in {destination}.\n\n{summary}"
    
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
                "keywords": "food tour",
                "type": "tourist_attraction"
            },
            "dining": {
                "keywords": "",
                "type": "restaurant"
            },
            "culture": {
                "keywords": "cultural attraction",
                "type": "museum"
            },
            "history": {
                "keywords": "historical site",
                "type": "museum"
            },
            "art": {
                "keywords": "art",
                "type": "museum"
            },
            "nature": {
                "keywords": "nature",
                "type": "park"
            },
            "shopping": {
                "keywords": "",
                "type": "shopping_mall"
            },
            "adventure": {
                "keywords": "adventure",
                "type": "tourist_attraction"
            },
            "relaxation": {
                "keywords": "spa",
                "type": "spa"
            }
        }
        
        # Default values
        default_params = {
            "keywords": interest,
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
            "moderate": 2,
            "luxury": 3
        }
        
        return budget_mapping.get(budget.lower())
    
    def _create_research_summary(self, attractions):
        """
        Create a summary of research findings.
        
        Args:
            attractions: List of attractions found
            
        Returns:
            Summary text
        """
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
                    rating = f" (Rating: {item.get('rating', 'N/A')})" if item.get("rating") else ""
                    summary += f"- {item.get('name', 'Unnamed')}{rating}\n"
            else:
                summary += "\n"
                
            summary += "\n"
        
        return summary