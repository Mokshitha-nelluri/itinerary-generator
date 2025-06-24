# Tools for finding attractions and restaurants at a destination

from google.adk.tools import FunctionTool
import json

def create_attraction_search_tool(gmaps_client):
    """
    Create an attraction search tool using the provided Google Maps client.
    
    Args:
        gmaps_client: Google Maps API client
        
    Returns:
        FunctionTool configured for attraction searching
    """
    
    async def attraction_search(location: str, keywords: str = None, type_filter: str = "tourist_attraction", radius: int = 5000):
        """
        Search for attractions near a location.
        
        Args:
            location: Location to search around (string like "San Francisco")
            keywords: Optional keywords to filter results (e.g. "museum")
            type_filter: Type of place to search for
            radius: Search radius in meters
            
        Returns:
            List of attractions with details
        """
        try:
            geocode_result = gmaps_client.geocode(location)
            if not geocode_result:
                return {"error": f"Could not find location: {location}"}
            
            lat = geocode_result[0]['geometry']['location']['lat']
            lng = geocode_result[0]['geometry']['location']['lng']

            search_params = {
                'location': (lat, lng),
                'radius': radius,
                'type': type_filter,
                'rank_by': 'prominence'
            }

            if keywords:
                search_params['keyword'] = keywords
            
            places_result = gmaps_client.places_nearby(**search_params)

            attractions = []
            for place in places_result.get('results', []):
                place_details = gmaps_client.place(place['place_id'], fields=[
                    'name', 'formatted_address', 'website', 'rating', 'price_level',
                    'opening_hours', 'formatted_phone_number', 'geometry', 'types', 'user_ratings_total'
                ])['result']

                attractions.append({
                    'name': place.get('name'),
                    'address': place.get('vicinity'),
                    'place_id': place.get('place_id'),
                    'rating': place.get('rating'),
                    'user_rating_total': place.get('user_ratings_total', 0),
                    'types': place.get('types'),
                    'location': place.get('geometry', {}).get('location'),
                    'opening_hours': place_details.get('opening_hours', {}).get('weekday_text', []),
                    'website': place_details.get('website', ''),
                    'phone': place_details.get('formatted_phone_number', '')
                })

            # Sort attractions by rating and user rating total
            sorted_attractions = sorted(
                attractions,
                key=lambda x: (x['rating'] or 0, x['user_rating_total']),
                reverse=True
            )
            return sorted_attractions[:15]
        
        except Exception as e:
            return {"error": f"Error searching for attractions: {str(e)}"}
    
    # Create and return the FunctionTool
    return FunctionTool(func=attraction_search)

def create_restaurant_search_tool(gmaps_client):
    """
    Create a restaurant search tool using the provided Google Maps client.
    
    Args:
        gmaps_client: Google Maps API client
        
    Returns:
        FunctionTool configured for restaurant searching
    """
    
    async def restaurant_search(location: str, cuisine: str = None, price_level: int = None, radius: int = 5000):
        """
        Search for restaurants near a location.

        Args: 
            location: Location to search around
            cuisine: Optional cuisine type
            price_level: Price level from 1(least expensive) to 4
            radius: Search radius in meters

        Returns:
            List of restaurants with details
        """
        try:
            geocode_result = gmaps_client.geocode(location)
            if not geocode_result:
                return {"error": f"Could not find location: {location}"}
            
            lat = geocode_result[0]['geometry']['location']['lat']
            lng = geocode_result[0]['geometry']['location']['lng']

            search_params = {
                'location': (lat, lng),
                'radius': radius,
                'type': 'restaurant'
            }

            if cuisine:
                search_params['keyword'] = cuisine

            places_result = gmaps_client.places_nearby(**search_params)

            restaurants = []
            for place in places_result.get('results', []):
                # Skip if price level doesn't match
                if price_level is not None and 'price_level' in place and place['price_level'] != price_level:
                    continue

                place_details = gmaps_client.place(place['place_id'], fields=[
                    'name', 'formatted_address', 'website', 'rating', 'price_level',
                    'opening_hours', 'formatted_phone_number', 'geometry', 'types', 'user_ratings_total'
                ])['result']

                restaurants.append({
                    'name': place.get('name'),
                    'address': place.get('vicinity'),
                    'place_id': place.get('place_id'),
                    'rating': place.get('rating'),
                    'user_rating_total': place.get('user_ratings_total', 0),
                    'price_level': place.get('price_level'),
                    'location': place.get('geometry', {}).get('location'),
                    'opening_hours': place_details.get('opening_hours', {}).get('weekday_text', []),
                    'website': place_details.get('website', ''),
                    'phone': place_details.get('formatted_phone_number', '')
                })
            
            sorted_restaurants = sorted(
                restaurants,
                key=lambda x: (x['rating'] or 0, x['user_rating_total']),
                reverse=True
            )

            return sorted_restaurants[:15]
            
        except Exception as e:
            return {"error": f"Error searching for restaurants: {str(e)}"}
    
    # Create and return the FunctionTool
    return FunctionTool(func=restaurant_search)

# Convenience function to create both tools at once
def create_location_tools(gmaps_client):
    """
    Create both attraction and restaurant search tools.
    
    Args:
        gmaps_client: Google Maps API client
        
    Returns:
        Tuple of (attraction_tool, restaurant_tool)
    """
    attraction_tool = create_attraction_search_tool(gmaps_client)
    restaurant_tool = create_restaurant_search_tool(gmaps_client)
    return attraction_tool, restaurant_tool



def create_lodging_search_tool(gmaps_client):
    async def lodging_tool(context, **kwargs):
        destination = kwargs.get("destination")  # city name
        radius = kwargs.get("radius", 3000)

        # Use geocoding to convert destination to lat/lng
        geocode = gmaps_client.geocode(destination)
        if not geocode:
            return {"error": f"Could not geocode destination: {destination}"}

        location = geocode[0]["geometry"]["location"]

        # Search for lodging near location
        response = gmaps_client.places_nearby(
            location=location,
            radius=radius,
            type="lodging"
        )

        return response.get("results", [])

    return FunctionTool(
        name="lodging_search",
        description="Finds lodging options near a destination using Google Maps",
        func=lodging_tool
    )
