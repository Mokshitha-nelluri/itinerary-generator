# Tools for finding attractions and restaurants at a destination

from google.adk.tools import FunctionTool
import json

class AttractionSearchTool(FunctionTool):
    def __init__(self, gmaps_client):
        """
        Initialize the attraction search tool.

        Args:
            gmaps_client: Google Maps API client
        """
        super().__init__(
            name= "attractions_search",
            description= "Search for attractions at a destination"
        )
        self.gmaps = gmaps_client

    #asynchronously searches for places 
    async def execute(self, location, keywords=None, type_filter="tourist attraction", radius=5000):
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
            geocode_result = self.gmaps.geocode(location)
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
            
            places_result = self.gmaps.places_nearby(**search_params)

            attractions = []
            for place in places_result.get('results', []):
                place_details = self.gmaps.place(place['place_id'], fields=[  #.place method fetches detailed info, identified by its place_id. fields- makes call faster and cheaper than requesting everything. gives more richer deatils than places_nearby.
                    'name', 'formatted_address', 'website', 'rating', 'price_level',
                    'opening_hours', 'formatted_phone_number', 'geometry', 'types', 'user_ratings_total'
                ])['result'] # specifying [result] ensures that only the actual place's deatiled info is extracted (i.e the info in result key), leaving out unnecessary keys that are returned by the api self.gmaps.place()

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

            # built in python sort function sorts the list of attraction dictinaries by rating, if ratings same them by no. of user ratings
            sorted_attractions = sorted(
                attractions,
                key = lambda x: (x['rating'] or 0, x['user_ratings_total']), #func builds a tuple (rating, no. of user ratings)
                reverse= True #default is asc, makes it desc
            )
            return sorted_attractions[:15]
        
        except Exception as e: #catches any unexpected errors and wraps them in a dict
            return {"error": f"Error searching for attractions: {str(e)}"} 

class RestaurantSearchTool(FunctionTool):
    def __init__(self, gmpas_client):
        """
        Initialize the restaurant search tool

        Args: 
            gmpas_client: Google maps API client

        """
        super().__init__(
            name="restaurant_search",
            description = "Search for restaurants at a destination"
        )
        self.gmaps = gmpas_client

        async def execute(self, location, cuisine=None, price_level=None, radius=5000):
            """ 
            Search for restaurants near a location.

            Args: 
                location: Location to search around.
                cuisine: optional cuisine type.
                price_level: Price level from 1(least expensive) to 4.
                radius: search radius in meters.

            Returns:
                List of restaurants with details.
            """

            try:
                geocode_result = self.gmaps.geocode(location)
                if not geocode_result:
                    return {"error": f"Could not find location: {location}"}
                
                lat = geocode_result[0]['geometry']['location']['lat']
                lng = geocode_result[0]['geometry']['location']['lng']

                search_params = {
                    'location': (lat,lng),
                    'radius': radius,
                    'type': 'restaurant'
                }

                if cuisine:
                    search_params['keyword'] = cuisine

                places_result = self.gmaps.places_nearby(**search_params)

                restaurants = []
                for place in places_result.get('results', []):
                    #skip if price level doesnt match
                    if price_level is not None and 'price_level' in place and place['price_level'] != price_level:
                        continue

                    place_details = self.gmaps.place(place['place_id'], fields=[
                        'name', 'formatted_address', 'website', 'rating', 'price_level',
                        'opening_hours', 'formatted_phone_number', 'geometry', 'types', 'user_ratings_total'
                    ])['result']

                    restaurants.append({
                        'name': place.get('name'),
                        'address': place.get('vicinity'),
                        'place_id': place.get('place_id'),
                        'rating': place.get('rating'),
                        'user_ratings_total': place.get('user_ratings_total', 0),
                        'price_level': place.get('price_level'),
                        'location': place.get('geometry', {}).get('location'),
                        'opening_hours': place_details.get('opening_hours', {}).get('weekday_text', []),
                        'website': place_details.get('website', ''),
                        'phone': place_details.get('formatted_phone_number', '')
                    })
                
                sorted_restaurants = sorted(
                    restaurants,
                    key= lambda x: (x['rating'] or 0, x['user_ratings_total']),
                    reverse = True
                )

                return sorted_restaurants[:15]
            except Exception as e:
                return {"error": f"Error searching for restaurants: {str(e)}"}

                  
### 
# Notes: 
# for place in places_result.get('results', [])[:15]:
# .get is a safe way to access dictionary keys. If results is not present, it returns deafult i.e empty list
# it is equivalent to writing an if-else statement.

#(**search_params):
# This is Python’s dictionary unpacking syntax, often called “keyword argument unpacking.” 
#unpacks the dictionary’s key-value pairs into separate keyword arguments.
#places_result = self.gmaps.places_nearby(**search_params)
# Equivalent to: places_result = self.gmaps.places_nearby(location=(lat, lng), radius=5000, type='tourist_attraction', keyword='museum'  # Only if keyword exists)
#useful to build dictionary dynamically


###