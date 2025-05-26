# Scheduling tools 

import asyncio
from google.adk.tools import FunctionTool
import json
import datetime
import aiohttp
import os 
import random
import google.generativeai as genai
from dotenv import load_dotenv
load_dotenv()

class ScheduleOptimizer(FunctionTool):
    def __init__(self, gmaps_client, llm_client=None):
        super().__init__(
            name = "schedule_optimizer",
            description = "Optimize the schedule of activities based on location, optimal visit times and opening hrs."
        )
        self.gmaps = gmaps_client
        self.gemini_api_key = os.getenv("GEMINI_API_KEY") #get from env var
        self.llm_client = self._setup_gemini_client() if self.gemini_api_key else None
        self.visit_info_cache = {} #cache for storing visit durations and optimal times

    def _setup_gemini_client(self):
        """Setup Gemini LLM client"""
        try:
            genai.configure(api_key=self.gemini_api_key)
            model = genai.GenerativeModel(model_name="gemini-pro")
            return model
        except Exception as e:
            print(f"Error setting up Gemini client: {str(e)}")
            return None


    async def execute(self, attractions, start_date, end_date, accomodation_location=None, start_time="9:00", end_time="21:00", return_to_accomodation=True):
        """
        Optimize the schedule of activities.
        
        Args:
            attractions: List of attractions to schedule
            start_date: Start date of the itinerary (YYYY-MM-DD)
            end_date: End date of the itinerary (YYYY-MM-DD)
            start_time: Preferred start time each day (HH:MM)
            end_time: Preferred end time each day (HH:MM)
            
        Returns:
            Optimized schedule
        """

        try:
            # Parsing the dates and calculating how many days the itinerary spans.
            start = datetime.datetime.strptime(start_date, "%Y-%m-%d") #converts string into datetime obj
            end = datetime.datetime.strptime(end_date,  "%Y-%m-%d")
            duration_days = (end-start).days + 1 # excludes the end date. add 1 to include end date
            start_time_obj = datetime.datetime.strptime(start_time, "%H:%M")
            end_time_obj = datetime.datetime.strptime(end_time, "%H:%M")

            # Prefetch visit durations and optimal visit times for all attractions
            await self.prefetch_visit_info(attractions)

            unscheduled_attractions = attractions.copy()

        
            daily_schedules = []

            if not accomodation_location and attractions: #fallback
                accomodation_location = attractions[0]['geometry']['location']
            # Loop through each day
            for day in range(duration_days):
                current_date = start + datetime.timedelta(days=day)
                current_time = datetime.datetime.combine(current_date.date(), start_time_obj.time()) # Tracker for when the user finishes one spot and moves to the next
                day_name = current_date.strftime("%A").lower()

                schedule = {
                    "date": current_date.strftime("%Y-%m-%d"),
                    "day": current_date.strftime("%A"),
                    "activities": []
                }
                if not unscheduled_attractions:
                    break
                
                # Filter attarctions based on opening hrs for current day
                today_viable_attractions = {
                    x for x in unscheduled_attractions if self.is_open_on_date(x, current_date)
                }

                if not today_viable_attractions:
                    schedule["note"] = "No attractions available for this day based on opening hours"
                    daily_schedules.append(schedule)
                    continue

                #start each day from accomodation
                current_location = accomodation_location


                # Sort attractions by optimal time of day and proximity
                day_attractions = self.sort_by_optimal_time_and_proximity(
                    current_location,
                    today_viable_attractions,
                    current_date
                )

                for attraction in day_attractions:
                    place_id = attraction.get('place_id', "unknown")
                    visit_info = self.visit_info_cache.get(place_id, {})

                    # get recommended duration from cache to estimate 
                    duration_hours = visit_info.get('recommended_duration', self.estimate_visit_duration(attraction))
                    duration_delta = datetime.timedelta(hours=duration_hours)
                    # Check if we have enough time left in the day
                    if current_time + duration_delta > datetime.datetime.combine(current_date.date(), end_time_obj.time()):
                        break
                    
                    #Travel time to the attraction
                    travel_minutes = await self.get_travel_time(current_location, attraction['geometry']['location'])
                    travel_delta = datetime.timedelta(minutes=travel_minutes)

                    arrival_time = current_time + travel_delta

                    schedule["activities"].append({
                        "start_time": arrival_time.strftime("%H:%M"),
                        "attraction": attraction,
                        "duration": f"{duration_hours: .1f} hours",
                        "optimal_time": visit_info.get('optimal_time', 'Not avaialable'),
                        "travel_time": f"{travel_minutes: .0f} minutes"


                    })

                    # remove the attraction from unscheduled
                    unscheduled_attractions.remove(attraction)
                    #update current location and time
                    current_time = arrival_time + duration_delta
                    current_location = attraction['geometry']['location']

                if return_to_accomodation and current_location != accomodation_location and schedule["activities"]:
                    travel_back_minutes = await self.get_travel_time(
                        current_location,
                        accomodation_location
                    )
                    end_time_with_travel = current_time + datetime.timedelta(minutes=travel_back_minutes)

                    schedule["return_to_accomodation"] = {
                        "departure_time": current_time.strftime("%H:%M"),
                        "travel_time": f"{travel_back_minutes:.0f} minutes",
                        "arrival_time": end_time_with_travel.strftime("%H:%M")
                    }

            
                daily_schedules.append(schedule)

            return daily_schedules
        
        except Exception as e:
            return {"error": f"Error optimizing schedule: {str(e)}"}
        
    async def prefetch_visit_info(self, attractions):
        """Pre-fetch visit information for all attractions to optimize API calls."""

        tasks = []
        for attraction in attractions:
            place_id = attraction.get('place_id', 'unkwown')
            if place_id not in self.visit_info_cache:
                tasks.append(self.get_visit_info(attraction))
        
        batch_size = 5 #To avoid rate limits
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i:i+batch_size]
            await asyncio.gather(*batch)

    async def get_visit_info(self, attraction):
        """Get recommended duration and optimal time to visit."""

        place_id = attraction.get('place_id', 'unkown')
        if place_id in self.visit_info_cache:
            return self.visit_info_cache[place_id]
        
        visit_info = {
            'recommended_duration': self.estimate_visit_duration(attraction),
            'optimal_time': 'Anytime during opening hours'
        }

        try:
            place_details = self.gmaps.place( # !!
                place_id=place_id,
                fields = ['opening_hours', 'reviews', 'url', 'user_ratings_total']
            )

            hours = place_details.get('opening_hours', {})
            reviews = place_details.get('reviews', [])
            #Sample reviews if too many
            sampled_reviews = self.sample_reviews(reviews)

            visit_info['recommeded_duration'] = self.calculate_duration(place_details, attraction)
            visit_info['optimal_time'] = self.determine_optimal_time(sampled_reviews)


            if self.llm_client:
                try:
                    name= attraction.get('name', '')
                    vicinity = attraction.get('vicinity', '')

                    llm_data = await self.get_visit_details_from_llm(
                        name, vicinity
                    )

                    if llm_data: #Only update if llm gave meaningful info
                        if llm_data.get('duration'):
                            visit_info['recommended_duration'] = llm_data['duration']
                        if llm_data.get('optimal_time'):
                            visit_info['optimal_time'] = llm_data['optimal_time']
                except Exception as e:
                    # If LLM fails, continue with the data we have
                    pass

        except Exception as e:
            # If API call fails, use our default estimates

            pass

        self.visit_info_cache[place_id] = visit_info
        return visit_info
    
    def sample_reviews(self, reviews, max_reviews=20):
        """Sample a subset of reviews if there are too many."""
        if not reviews or len(reviews) <= max_reviews:
            return reviews
        
        # First, try to find reviews that mention time
        time_keywords = ['morning', 'afternoon', 'evening', 'night', 'early', 'late', 
                         'busy', 'crowd', 'quiet', 'hour', 'time', 'wait', 'line']
        
        time_reviews = []
        other_reviews = []
        
        for review in reviews:
            text = review.get('text', '').lower()
            if any(keyword in text for keyword in time_keywords):
                time_reviews.append(review)
            else:
                other_reviews.append(review)
        
        # If we have enough time-related reviews, prioritize those
        if len(time_reviews) >= max_reviews // 2:
            # Take half from time reviews, half from random others
            sampled_time = random.sample(time_reviews, min(len(time_reviews), max_reviews // 2))
            remaining_slots = max_reviews - len(sampled_time)
            
            if remaining_slots > 0 and other_reviews:
                sampled_other = random.sample(other_reviews, min(len(other_reviews), remaining_slots))
                return sampled_time + sampled_other
            return sampled_time
        
        # Otherwise, just sample randomly
        return random.sample(reviews, max_reviews)

    
    def calculate_duration(self, place_details, attraction):
        """ Calculate a more accurate duration"""
        base_duration = self.estimate_visit_duration(attraction)
        # Use rating data to refine our estimate
        rating = place_details.get('rating', 0)
        rating_count = place_details.get('user_ratings_total', 0)

        # Get mentions of time in reviews
        duration_from_reviews = self.extract_duration_from_reviews(place_details.get('reviews', []))
        if duration_from_reviews:
            return duration_from_reviews
        elif rating >= 4.5 and rating_count > 1000: # Highly rated attractions often take longer to enjoy
            return base_duration * 1.2
        elif rating <= 3.5 and rating_count > 500:  # Lower rated attractions might not be worth as much time
            return base_duration * 0.8
        else:
            return base_duration
        
    def extract_duration_from_reviews(self, reviews):
        """Extract mentions of visit duration from reviews."""
        time_keywords = {
            'hour': 1.0,
            'hours': 1.0,
            'hr': 1.0,
            'hrs': 1.0,
            'all day': 6.0,
            'half an hour': 0.5,
            'half day': 4.0,
            'minutes': 1/60
        }
            
        durations = []
        for review in reviews:
            text = review.get('text', '').lower()
            for keyword, mutliplier in time_keywords.items():
                if keyword in text: # Look for numbers before the keyword
                    words = text.split()
                    for i, word in enumerate(words):
                        if keyword in word and i>0:
                            try:
                                value = float(words[i-1])
                                durations.append(value * mutliplier)
                                break
                            except ValueError:
                                number_words = {
                                    'one': 1, 'two': 2, 'three': 3, 'four': 4, 
                                    'five': 5, 'six': 6, 'seven': 7, 'eight': 8
                                }

                                if words[i-1] in number_words:
                                    durations.append(number_words[words[i-1]] * mutliplier)
                                    break
        # If found enough duration mentions, use median value
        if len(durations) >= 3:
            durations.sort()
            return durations[len(durations) // 2]
        elif durations:
            return sum(durations) / len(durations) #avg
        else:
            return None
    
    def determine_optimal_time(self, hours, reviews):
        """Determine the optimal time to visit based on hours and reviews."""


        default = "Anytime during opening hours"
        
        time_mentions = self.extract_time_mentions_from_reviews(reviews)
        if time_mentions:
            return time_mentions

         
        try:
            # Get opening periods for days of the week
            periods = hours.get('periods', [])
            if periods:
                # Check for limited hours or special patterns
                optimal_time = self._analyze_opening_hours(periods)
                if optimal_time:
                    return optimal_time
        except Exception:
            pass
        
        # Make educated guesses based on place type
        place_types = []
        for review in reviews:
            text = review.get('text', '').lower()
            
            # Look for mentions of place types
            if 'museum' in text or 'gallery' in text:
                place_types.append('cultural')
            if 'beach' in text or 'park' in text:
                place_types.append('outdoor')
            if 'restaurant' in text or 'cafe' in text or 'food' in text:
                place_types.append('dining')
            if 'shopping' in text or 'shop' in text or 'store' in text:
                place_types.append('shopping')
            if 'crowd' in text or 'busy' in text or 'queue' in text or 'line' in text:
                place_types.append('popular')
            
        # Count frequencies
        from collections import Counter
        type_counter = Counter(place_types)
        
        # Make recommendations based on the most common type
        if type_counter:
            most_common_type = type_counter.most_common(1)[0][0]
            
            if most_common_type == 'cultural':
                return "Weekday mornings are typically less crowded for museums and galleries"
            elif most_common_type == 'outdoor':
                return "Early morning or late afternoon for the best lighting and fewer crowds"
            elif most_common_type == 'dining':
                return "Arrive just before or after typical meal rush hours (avoid 12-2pm and 6-8pm)"
            elif most_common_type == 'shopping':
                return "Weekday mornings typically have the fewest shoppers"
            elif most_common_type == 'popular':
                return "Early morning shortly after opening time to avoid crowds"

        
        return default

    def _analyze_opening_hours(self, periods):
        """Analyze opening hours to find patterns that suggest optimal visiting times."""
        # Check for limited opening days
        days_open = len(periods)
        
        if days_open < 7:
            # If only open certain days, those may be busier
            return "This location has limited opening days, which may be busier than typical attractions"
            
        # Check for unusual hours that might suggest good times to visit
        unusual_openings = []
        unusual_closings = []
        
        for period in periods:
            if 'open' in period and 'close' in period:
                open_time = period['open'].get('time', '0000')
                close_time = period['close'].get('time', '0000')
                
                # Convert to hours as integers
                open_hour = int(open_time[:2])
                close_hour = int(close_time[:2])
                
                # Check for early openings (before 9 AM)
                if open_hour < 9:
                    unusual_openings.append(open_hour)
                    
                # Check for late closings (after 6 PM)
                if close_hour > 18:
                    unusual_closings.append(close_hour)
        
        # If place opens very early, recommend early visits
        if unusual_openings:
            avg_early_open = sum(unusual_openings) / len(unusual_openings)
            if avg_early_open <= 7:
                return f"Opens early at {int(avg_early_open)}:00 - early morning visits likely less crowded"
                
        # If place closes late, recommend late visits
        if unusual_closings:
            avg_late_close = sum(unusual_closings) / len(unusual_closings)
            if avg_late_close >= 20:
                return f"Open until {int(avg_late_close)}:00 - evening visits often less crowded"
                
        # Check for midday closures that might indicate optimal patterns
        has_midday_closure = False
        for period in periods:
            if 'open' in period and 'close' in period:
                close_time = period['close'].get('time', '0000')
                close_hour = int(close_time[:2])
                
                if 11 <= close_hour <= 15:  # Closes during midday
                    has_midday_closure = True
                    
        if has_midday_closure:
            return "Location may close during midday - check specific hours and plan around these breaks"
            
        return None

    def extract_time_mentions_from_reviews(self, reviews):
        """Extract mentions of good times to visit from reviews."""
        if not reviews:
            return None
            
        # Time-related phrases to look for
        time_phrases = {
            'morning': ['morning', 'early', 'sunrise', 'breakfast time', 'dawn', 'am', 'open'],
            'midday': ['noon', 'lunch', 'midday', 'afternoon', 'middle of day'],
            'evening': ['evening', 'sunset', 'dusk', 'late', 'night', 'dinner time', 'pm', 'close'],
            'crowd': ['crowd', 'busy', 'line', 'queue', 'wait', 'packed', 'full', 
                     'avoid', 'quiet', 'peaceful', 'empty', 'less people']
        }
        
        # Track mentions of different times and sentiments
        time_sentiments = {
            'morning': {'positive': 0, 'negative': 0},
            'midday': {'positive': 0, 'negative': 0},
            'evening': {'positive': 0, 'negative': 0}
        }
        
        # Words indicating positive or negative context
        positive_indicators = ['good', 'great', 'best', 'recommend', 'perfect', 'ideal', 'quiet', 
                              'peaceful', 'empty', 'less', 'fewer', 'not busy', 'not crowded']
        negative_indicators = ['bad', 'avoid', 'busy', 'crowded', 'packed', 'full', 'long wait', 
                              'too many', 'lots of people', 'tourist', 'rush']
        
        relevant_sentences = []
        
        # Process each review
        for review in reviews:
            text = review.get('text', '').lower()
            
            # Split into sentences for better context analysis
            sentences = text.split('. ')
            for sentence in sentences:
                has_time_mention = False
                time_period = None
                
                # Check if sentence contains time-related phrases
                for period, phrases in time_phrases.items():
                    if any(phrase in sentence for phrase in phrases):
                        has_time_mention = True
                        if period != 'crowd':  # 'crowd' isn't a time period
                            time_period = period
                
                # If sentence mentions time and crowds/busyness
                if has_time_mention and time_period and any(phrase in sentence for phrase in time_phrases['crowd']):
                    relevant_sentences.append(sentence)
                    
                    # Determine sentiment for this time mention
                    is_positive = any(ind in sentence for ind in positive_indicators)
                    is_negative = any(ind in sentence for ind in negative_indicators)
                    
                    # Update sentiment counts
                    if is_positive and not is_negative:
                        time_sentiments[time_period]['positive'] += 1
                    elif is_negative and not is_positive:
                        time_sentiments[time_period]['negative'] += 1
        
        # If we have relevant sentences, analyze the patterns
        if relevant_sentences:
            # Find the best time period based on sentiment analysis
            best_period = None
            best_score = -1
            
            for period, sentiment in time_sentiments.items():
                # Calculate a simple score: positive mentions minus negative mentions
                score = sentiment['positive'] - sentiment['negative']
                if score > best_score:
                    best_score = score
                    best_period = period
                    
            worst_period = None
            worst_score = float('inf')
            
            for period, sentiment in time_sentiments.items():
                # Calculate inverse score for worst time
                score = sentiment['negative'] - sentiment['positive']
                if score > 0 and score < worst_score:
                    worst_score = score
                    worst_period = period
            
            # Generate recommendation
            recommendation = ""
            if best_period and best_score > 0:
                recommendation += f"{best_period.capitalize()} is recommended based on visitor reviews"
                
                # Add examples from relevant sentences (max 2)
                if len(relevant_sentences) > 0:
                    # Pick the most relevant sentence that mentions the best period
                    best_examples = [s for s in relevant_sentences 
                                    if any(phrase in s for phrase in time_phrases[best_period])][:1]
                    if best_examples:
                        recommendation += f". Example: '{best_examples[0].capitalize()}'"
            
            # Add what to avoid if we have that information
            if worst_period and worst_score > 0:
                if recommendation:
                    recommendation += f"; avoid {worst_period} if possible"
                else:
                    recommendation = f"Consider avoiding {worst_period} when it may be more crowded"
            
            return recommendation
                
        # If not enough relevant mentions, check simple patterns
        morning_mentions = sum(1 for r in reviews for phrase in time_phrases['morning'] 
                             if phrase in r.get('text', '').lower())
        midday_mentions = sum(1 for r in reviews for phrase in time_phrases['midday'] 
                             if phrase in r.get('text', '').lower())
        evening_mentions = sum(1 for r in reviews for phrase in time_phrases['evening'] 
                             if phrase in r.get('text', '').lower())
        
        # If we have a clear winner with simple counting
        counts = [('morning', morning_mentions), ('midday', midday_mentions), ('evening', evening_mentions)]
        max_count = max(counts, key=lambda x: x[1])
        
        if max_count[1] > 3 and max_count[1] > sum(c[1] for c in counts if c[0] != max_count[0]):
            return f"{max_count[0].capitalize()} is mentioned most frequently in reviews"
            
        return None


    
    async def get_visit_details_from_llm(self, attraction_name, location):
        """Query Gemini to get recommended duration and best time to visit."""
        query = f"How long does it typically take to visit {attraction_name} in {location}? What's the best time of day to visit to avoid crowds? Respond with duration in hours (e.g. 2.5 hours) and time of day recommendations."
        
        try:
            if not self.llm_client:
                return None
                
            # Call Gemini API
            response = await asyncio.to_thread(
                self.llm_client.generate_content,
                query
            )
            
            # Parse the response
            parsed = self.parse_llm_response(response)
            return parsed
        except Exception as e:
            print(f"Error with LLM: {str(e)}")
            return None

    
    def parse_llm_response(self, response):
        """Parse LLM response to extract duration and optimal time."""
        # Implementation depends on your LLM API response format
        # This is a simplified example
        text = response.text if hasattr(response, 'text') else str(response)
        
        result = {
            'duration': None,
            'optimal_time': None
        }
        
        # Look for duration mentions
        duration_patterns = [
            r'(\d+(?:\.\d+)?)\s*(?:hour|hr)s?',
            r'(\d+)\s*-\s*(\d+)\s*(?:hour|hr)s?',
            r'(?:takes|duration|visit|spend)\s*(?:about|around)?\s*(\d+(?:\.\d+)?)\s*(?:hour|hr)s?'
        ]
        
        for pattern in duration_patterns:
            import re
            matches = re.search(pattern, text, re.IGNORECASE)
            if matches:
                if len(matches.groups()) > 1:
                    # Range pattern with two numbers
                    min_duration = float(matches.group(1))
                    max_duration = float(matches.group(2))
                    result['duration'] = (min_duration + max_duration) / 2
                else:
                    result['duration'] = float(matches.group(1))
                break
        
        # Look for optimal time mentions
        time_patterns = [
            r'best time (?:to visit|for visiting) is (?:in the )?(morning|afternoon|evening|night)',
            r'(morning|afternoon|evening|night) is (?:the )?(?:best|optimal|ideal|recommended)',
            r'visit (?:during|in) (?:the )?(morning|afternoon|evening|early|late)'
        ]
        
        for pattern in time_patterns:
            matches = re.search(pattern, text, re.IGNORECASE)
            if matches:
                result['optimal_time'] = f"{matches.group(1).capitalize()} is recommended"
                break
                
        # If we didn't find clear patterns, look for sentences with time keywords
        if not result['optimal_time']:
            time_keywords = ['crowd', 'busy', 'quiet', 'wait', 'line', 'queue']
            sentences = text.split('. ')
            
            for sentence in sentences:
                if any(keyword in sentence.lower() for keyword in time_keywords):
                    result['optimal_time'] = sentence.strip()
                    break
        
        return result

    def estimate_visit_duration(self, attraction):
        """Estimate duration based on API data or fallback defaults."""
        # Try getting a rough idea using rating count or type
        name = attraction.get("name", "").lower()
        types = attraction.get("types", [])
        rating_count = attraction.get("user_ratings_total", 0)

        # More sophisticated estimation logic
        if "museum" in types:
            if rating_count >= 10000:  # Major museums
                return 3.0
            elif rating_count >= 5000:
                return 2.5
            else:
                return 2.0
        elif "art_gallery" in types:
            return 1.5
        elif "park" in types:
            # Parks generally take longer
            if rating_count >= 5000:  # Major parks
                return 2.5
            else:
                return 1.5
        elif "zoo" in types or "aquarium" in types:
            return 3.0
        elif "amusement_park" in types or "theme_park" in types:
            return 4.0
        elif "beach" in types:
            return 2.5
        elif "shopping_mall" in types:
            return 2.0
        elif "restaurant" in types or "cafe" in types:
            return 1.5  # Typical meal time
        elif "historic" in name or "castle" in name or "palace" in name:
            return 2.0
        elif "cathedral" in name or "church" in name or "temple" in name or "shrine" in name:
            return 1.0
        elif "garden" in name:
            return 1.5
        elif "landmark" in types or "monument" in types:
            return 1.0
        # Adjust by popularity too
        elif rating_count >= 10000:
            return 2.5
        elif rating_count >= 5000:
            return 2.0
        elif rating_count >= 1000:
            return 1.5
        else:
            return 1.0  # Default fallback

    def is_open_on_date(self, attraction, date):
        """Check if an attraction is open on a given date."""
        place_id = attraction.get('place_id', 'unknown')
        visit_info = self.visit_info_cache.get(place_id, {})
        
        # Default to open if no data
        if not visit_info:
            return True
            
        # TODO: Implement proper opening hours checking
        # This would require parsing the opening_hours field from Places API
        return True

    def sort_by_optimal_time_and_proximity(self, start_location, attractions, current_date):
        """Sort attractions using both optimal visit time and proximity."""
        # Create a scored list of attractions based on optimal time and proximity
        scored_attractions = []
        current_hour = current_date.hour if hasattr(current_date, 'hour') else 9  # Default to morning
        
        for attraction in attractions:
            place_id = attraction.get('place_id', 'unknown')
            visit_info = self.visit_info_cache.get(place_id, {})
            optimal_time = visit_info.get('optimal_time', '').lower()
            
            # Score based on optimal time
            time_score = 0
            if 'morning' in optimal_time and current_hour < 12:
                time_score = 3
            elif 'afternoon' in optimal_time and 12 <= current_hour < 17:
                time_score = 3
            elif 'evening' in optimal_time and current_hour >= 17:
                time_score = 3
            
            # Will add proximity score later
            scored_attractions.append((attraction, time_score))
        
        # Sort first by time score
        scored_attractions.sort(key=lambda x: x[1], reverse=True)
        
        # Group by time score
        grouped = {}
        for attraction, score in scored_attractions:
            if score not in grouped:
                grouped[score] = []
            grouped[score].append(attraction)
        
        # Sort each group by proximity
        result = []
        current = start_location
        
        # Process each score group in descending order
        for score in sorted(grouped.keys(), reverse=True):
            group = grouped[score]
            while group:
                # Find nearest attraction in this group
                distances = self.gmaps.distance_matrix(
                    origins=[current],
                    destinations=[a['geometry']['location'] for a in group],
                    mode="driving",
                    units="metric"
                )
                
                durations = distances["rows"][0]["elements"]
                min_index = min(range(len(durations)), 
                               key=lambda i: durations[i]["duration"]["value"])
                
                nearest = group.pop(min_index)
                result.append(nearest)
                current = nearest['geometry']['location']
        
        return result

    async def get_travel_time(self, origin, destination, mode="driving"):
        """Use Distance Matrix API to get travel time in minutes."""
        try:
            result = self.gmaps.distance_matrix(
                origins=[origin],
                destinations=[destination],
                mode=mode,
                units="metric"
            )
            duration = result["rows"][0]["elements"][0]["duration"]["value"]  # in seconds
            return duration / 60  # convert to minutes
        except Exception:
            return 30  # fallback if API fails


class DistanceMatrixTool(FunctionTool):
    """Tool for calculating distances between locations."""

    def __init__(self, gmaps_client):
        super().__init__(
            name="distance_matrix",
            description="Calculate distances and travel times between locations"
        )
        self.gmaps = gmaps_client

    async def execute(self, origins, destinations, mode="driving"):
        try:
            result = self.gmaps.distance_matrix(
                origins=origins,
                destinations=destinations,
                mode=mode,
                units="metric"
            )
            return result
        except Exception as e:
            return {"error": f"Error calculating distances: {str(e)}"}


