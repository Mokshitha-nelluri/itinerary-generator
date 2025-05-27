# Scheduling tools - Refactored

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

# Global cache and clients
visit_info_cache = {}
gmaps_client = None
gemini_client = None

def setup_clients(gmaps, gemini_api_key=None):
    """Initialize global clients"""
    global gmaps_client, gemini_client
    gmaps_client = gmaps
    
    if gemini_api_key:
        try:
            genai.configure(api_key=gemini_api_key)
            gemini_client = genai.GenerativeModel(model_name="gemini-pro")
        except Exception as e:
            print(f"Error setting up Gemini client: {str(e)}")
            gemini_client = None

async def optimize_schedule(attractions, start_date, end_date, accommodation_location=None, 
                          start_time="9:00", end_time="21:00", return_to_accommodation=True):
    """
    Optimize the schedule of activities.
    
    Args:
        attractions: List of attractions to schedule
        start_date: Start date of the itinerary (YYYY-MM-DD)
        end_date: End date of the itinerary (YYYY-MM-DD)
        accommodation_location: Starting/ending location each day
        start_time: Preferred start time each day (HH:MM)
        end_time: Preferred end time each day (HH:MM)
        return_to_accommodation: Whether to end each day at accommodation
        
    Returns:
        Optimized schedule
    """
    try:
        # Parse dates and calculate duration
        start = datetime.datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.datetime.strptime(end_date, "%Y-%m-%d")
        duration_days = (end - start).days + 1
        start_time_obj = datetime.datetime.strptime(start_time, "%H:%M")
        end_time_obj = datetime.datetime.strptime(end_time, "%H:%M")

        # Prefetch visit information for all attractions
        await prefetch_visit_info(attractions)

        unscheduled_attractions = attractions.copy()
        daily_schedules = []

        # Use first attraction as fallback accommodation location
        if not accommodation_location and attractions:
            accommodation_location = attractions[0]['geometry']['location']

        # Schedule each day
        for day in range(duration_days):
            current_date = start + datetime.timedelta(days=day)
            current_time = datetime.datetime.combine(current_date.date(), start_time_obj.time())

            schedule = {
                "date": current_date.strftime("%Y-%m-%d"),
                "day": current_date.strftime("%A"),
                "activities": []
            }

            if not unscheduled_attractions:
                break

            # Filter attractions that are open today
            today_viable_attractions = [
                x for x in unscheduled_attractions 
                if is_open_on_date(x, current_date)
            ]

            if not today_viable_attractions:
                schedule["note"] = "No attractions available for this day based on opening hours"
                daily_schedules.append(schedule)
                continue

            # Start each day from accommodation
            current_location = accommodation_location

            # Sort attractions by optimal time and proximity
            day_attractions = await sort_by_optimal_time_and_proximity(
                current_location, today_viable_attractions, current_date
            )

            # Schedule attractions for the day
            for attraction in day_attractions:
                place_id = attraction.get('place_id', "unknown")
                visit_info = visit_info_cache.get(place_id, {})

                # Get recommended duration
                duration_hours = visit_info.get('recommended_duration', estimate_visit_duration(attraction))
                duration_delta = datetime.timedelta(hours=duration_hours)

                # Check if we have enough time left in the day
                if current_time + duration_delta > datetime.datetime.combine(current_date.date(), end_time_obj.time()):
                    break

                # Calculate travel time to attraction
                travel_minutes = await get_travel_time(current_location, attraction['geometry']['location'])
                travel_delta = datetime.timedelta(minutes=travel_minutes)
                arrival_time = current_time + travel_delta

                schedule["activities"].append({
                    "start_time": arrival_time.strftime("%H:%M"),
                    "attraction": attraction,
                    "duration": f"{duration_hours:.1f} hours",
                    "optimal_time": visit_info.get('optimal_time', 'Not available'),
                    "travel_time": f"{travel_minutes:.0f} minutes"
                })

                # Update for next iteration
                unscheduled_attractions.remove(attraction)
                current_time = arrival_time + duration_delta
                current_location = attraction['geometry']['location']

            # Add return to accommodation if requested
            if (return_to_accommodation and current_location != accommodation_location 
                and schedule["activities"]):
                travel_back_minutes = await get_travel_time(current_location, accommodation_location)
                end_time_with_travel = current_time + datetime.timedelta(minutes=travel_back_minutes)

                schedule["return_to_accommodation"] = {
                    "departure_time": current_time.strftime("%H:%M"),
                    "travel_time": f"{travel_back_minutes:.0f} minutes",
                    "arrival_time": end_time_with_travel.strftime("%H:%M")
                }

            daily_schedules.append(schedule)

        return daily_schedules

    except Exception as e:
        return {"error": f"Error optimizing schedule: {str(e)}"}

async def prefetch_visit_info(attractions):
    """Pre-fetch visit information for all attractions to optimize API calls."""
    tasks = []
    for attraction in attractions:
        place_id = attraction.get('place_id', 'unknown')
        if place_id not in visit_info_cache:
            tasks.append(get_visit_info(attraction))

    # Process in batches to avoid rate limits
    batch_size = 5
    for i in range(0, len(tasks), batch_size):
        batch = tasks[i:i+batch_size]
        await asyncio.gather(*batch)

async def get_visit_info(attraction):
    """Get recommended duration and optimal time to visit."""
    place_id = attraction.get('place_id', 'unknown')
    if place_id in visit_info_cache:
        return visit_info_cache[place_id]

    visit_info = {
        'recommended_duration': estimate_visit_duration(attraction),
        'optimal_time': 'Anytime during opening hours'
    }

    try:
        # Get place details from Google Maps
        place_details = gmaps_client.place(
            place_id=place_id,
            fields=['opening_hours', 'reviews', 'url', 'user_ratings_total']
        )

        hours = place_details.get('opening_hours', {})
        reviews = place_details.get('reviews', [])
        sampled_reviews = sample_reviews(reviews)

        visit_info['recommended_duration'] = calculate_duration(place_details, attraction)
        visit_info['optimal_time'] = determine_optimal_time(hours, sampled_reviews)

        # Enhance with LLM if available
        if gemini_client:
            try:
                name = attraction.get('name', '')
                vicinity = attraction.get('vicinity', '')
                llm_data = await get_visit_details_from_llm(name, vicinity)

                if llm_data:
                    if llm_data.get('duration'):
                        visit_info['recommended_duration'] = llm_data['duration']
                    if llm_data.get('optimal_time'):
                        visit_info['optimal_time'] = llm_data['optimal_time']
            except Exception:
                pass  # Continue with what we have

    except Exception:
        pass  # Use default estimates

    visit_info_cache[place_id] = visit_info
    return visit_info

def sample_reviews(reviews, max_reviews=20):
    """Sample a subset of reviews, prioritizing time-related content."""
    if not reviews or len(reviews) <= max_reviews:
        return reviews

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

    # Prioritize time-related reviews
    if len(time_reviews) >= max_reviews // 2:
        sampled_time = random.sample(time_reviews, min(len(time_reviews), max_reviews // 2))
        remaining_slots = max_reviews - len(sampled_time)
        
        if remaining_slots > 0 and other_reviews:
            sampled_other = random.sample(other_reviews, min(len(other_reviews), remaining_slots))
            return sampled_time + sampled_other
        return sampled_time

    return random.sample(reviews, max_reviews)

def calculate_duration(place_details, attraction):
    """Calculate a more accurate duration based on place details."""
    base_duration = estimate_visit_duration(attraction)
    
    rating = place_details.get('rating', 0)
    rating_count = place_details.get('user_ratings_total', 0)

    # Try to extract duration from reviews first
    duration_from_reviews = extract_duration_from_reviews(place_details.get('reviews', []))
    if duration_from_reviews:
        return duration_from_reviews
    elif rating >= 4.5 and rating_count > 1000:
        return base_duration * 1.2  # Highly rated places deserve more time
    elif rating <= 3.5 and rating_count > 500:
        return base_duration * 0.8  # Lower rated places might not need as much time
    else:
        return base_duration

def extract_duration_from_reviews(reviews):
    """Extract mentions of visit duration from reviews."""
    time_keywords = {
        'hour': 1.0, 'hours': 1.0, 'hr': 1.0, 'hrs': 1.0,
        'all day': 6.0, 'half an hour': 0.5, 'half day': 4.0,
        'minutes': 1/60
    }

    durations = []
    for review in reviews:
        text = review.get('text', '').lower()
        for keyword, multiplier in time_keywords.items():
            if keyword in text:
                words = text.split()
                for i, word in enumerate(words):
                    if keyword in word and i > 0:
                        try:
                            value = float(words[i-1])
                            durations.append(value * multiplier)
                            break
                        except ValueError:
                            number_words = {
                                'one': 1, 'two': 2, 'three': 3, 'four': 4,
                                'five': 5, 'six': 6, 'seven': 7, 'eight': 8
                            }
                            if words[i-1] in number_words:
                                durations.append(number_words[words[i-1]] * multiplier)
                                break

    # Return median if we have enough data points, otherwise average
    if len(durations) >= 3:
        durations.sort()
        return durations[len(durations) // 2]
    elif durations:
        return sum(durations) / len(durations)
    else:
        return None

def determine_optimal_time(hours, reviews):
    """Determine the optimal time to visit based on hours and reviews."""
    default = "Anytime during opening hours"
    
    # First check reviews for time mentions
    time_mentions = extract_time_mentions_from_reviews(reviews)
    if time_mentions:
        return time_mentions

    # Analyze opening hours patterns
    try:
        periods = hours.get('periods', [])
        if periods:
            optimal_time = analyze_opening_hours(periods)
            if optimal_time:
                return optimal_time
    except Exception:
        pass

    # Make educated guesses based on review content
    place_types = []
    for review in reviews:
        text = review.get('text', '').lower()
        
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

    if place_types:
        from collections import Counter
        type_counter = Counter(place_types)
        most_common_type = type_counter.most_common(1)[0][0]
        
        recommendations = {
            'cultural': "Weekday mornings are typically less crowded for museums and galleries",
            'outdoor': "Early morning or late afternoon for the best lighting and fewer crowds",
            'dining': "Arrive just before or after typical meal rush hours (avoid 12-2pm and 6-8pm)",
            'shopping': "Weekday mornings typically have the fewest shoppers",
            'popular': "Early morning shortly after opening time to avoid crowds"
        }
        
        return recommendations.get(most_common_type, default)
    
    return default

def analyze_opening_hours(periods):
    """Analyze opening hours to find patterns that suggest optimal visiting times."""
    days_open = len(periods)
    
    if days_open < 7:
        return "This location has limited opening days, which may be busier than typical attractions"
    
    # Check for unusual hours
    unusual_openings = []
    unusual_closings = []
    
    for period in periods:
        if 'open' in period and 'close' in period:
            open_time = period['open'].get('time', '0000')
            close_time = period['close'].get('time', '0000')
            
            open_hour = int(open_time[:2])
            close_hour = int(close_time[:2])
            
            if open_hour < 9:
                unusual_openings.append(open_hour)
            if close_hour > 18:
                unusual_closings.append(close_hour)
    
    if unusual_openings:
        avg_early_open = sum(unusual_openings) / len(unusual_openings)
        if avg_early_open <= 7:
            return f"Opens early at {int(avg_early_open)}:00 - early morning visits likely less crowded"
    
    if unusual_closings:
        avg_late_close = sum(unusual_closings) / len(unusual_closings)
        if avg_late_close >= 20:
            return f"Open until {int(avg_late_close)}:00 - evening visits often less crowded"
    
    return None

def extract_time_mentions_from_reviews(reviews):
    """Extract mentions of good times to visit from reviews."""
    if not reviews:
        return None

    time_phrases = {
        'morning': ['morning', 'early', 'sunrise', 'breakfast time', 'dawn', 'am', 'open'],
        'midday': ['noon', 'lunch', 'midday', 'afternoon', 'middle of day'],
        'evening': ['evening', 'sunset', 'dusk', 'late', 'night', 'dinner time', 'pm', 'close'],
        'crowd': ['crowd', 'busy', 'line', 'queue', 'wait', 'packed', 'full', 
                 'avoid', 'quiet', 'peaceful', 'empty', 'less people']
    }

    time_sentiments = {
        'morning': {'positive': 0, 'negative': 0},
        'midday': {'positive': 0, 'negative': 0},
        'evening': {'positive': 0, 'negative': 0}
    }

    positive_indicators = ['good', 'great', 'best', 'recommend', 'perfect', 'ideal', 'quiet', 
                          'peaceful', 'empty', 'less', 'fewer', 'not busy', 'not crowded']
    negative_indicators = ['bad', 'avoid', 'busy', 'crowded', 'packed', 'full', 'long wait', 
                          'too many', 'lots of people', 'tourist', 'rush']

    relevant_sentences = []

    # Process each review
    for review in reviews:
        text = review.get('text', '').lower()
        sentences = text.split('. ')
        
        for sentence in sentences:
            has_time_mention = False
            time_period = None
            
            # Check if sentence contains time-related phrases
            for period, phrases in time_phrases.items():
                if any(phrase in sentence for phrase in phrases):
                    has_time_mention = True
                    if period != 'crowd':
                        time_period = period

            # If sentence mentions time and crowds/busyness
            if has_time_mention and time_period and any(phrase in sentence for phrase in time_phrases['crowd']):
                relevant_sentences.append(sentence)
                
                is_positive = any(ind in sentence for ind in positive_indicators)
                is_negative = any(ind in sentence for ind in negative_indicators)
                
                if is_positive and not is_negative:
                    time_sentiments[time_period]['positive'] += 1
                elif is_negative and not is_positive:
                    time_sentiments[time_period]['negative'] += 1

    # Analyze sentiment patterns
    if relevant_sentences:
        best_period = None
        best_score = -1
        
        for period, sentiment in time_sentiments.items():
            score = sentiment['positive'] - sentiment['negative']
            if score > best_score:
                best_score = score
                best_period = period

        if best_period and best_score > 0:
            return f"{best_period.capitalize()} is recommended based on visitor reviews"

    return None

async def get_visit_details_from_llm(attraction_name, location):
    """Query Gemini to get recommended duration and best time to visit."""
    query = f"How long does it typically take to visit {attraction_name} in {location}? What's the best time of day to visit to avoid crowds? Respond with duration in hours (e.g. 2.5 hours) and time of day recommendations."
    
    try:
        if not gemini_client:
            return None
            
        response = await asyncio.to_thread(
            gemini_client.generate_content,
            query
        )
        
        return parse_llm_response(response)
    except Exception as e:
        print(f"Error with LLM: {str(e)}")
        return None

def parse_llm_response(response):
    """Parse LLM response to extract duration and optimal time."""
    text = response.text if hasattr(response, 'text') else str(response)
    
    result = {'duration': None, 'optimal_time': None}
    
    # Look for duration mentions
    import re
    duration_patterns = [
        r'(\d+(?:\.\d+)?)\s*(?:hour|hr)s?',
        r'(\d+)\s*-\s*(\d+)\s*(?:hour|hr)s?',
        r'(?:takes|duration|visit|spend)\s*(?:about|around)?\s*(\d+(?:\.\d+)?)\s*(?:hour|hr)s?'
    ]
    
    for pattern in duration_patterns:
        matches = re.search(pattern, text, re.IGNORECASE)
        if matches:
            if len(matches.groups()) > 1:
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
    
    return result

def estimate_visit_duration(attraction):
    """Estimate duration based on attraction type and popularity."""
    name = attraction.get("name", "").lower()
    types = attraction.get("types", [])
    rating_count = attraction.get("user_ratings_total", 0)

    # Duration by type
    type_durations = {
        "museum": 3.0 if rating_count >= 10000 else 2.5 if rating_count >= 5000 else 2.0,
        "art_gallery": 1.5,
        "park": 2.5 if rating_count >= 5000 else 1.5,
        "zoo": 3.0,
        "aquarium": 3.0,
        "amusement_park": 4.0,
        "theme_park": 4.0,
        "beach": 2.5,
        "shopping_mall": 2.0,
        "restaurant": 1.5,
        "cafe": 1.5
    }

    # Check for specific types
    for attraction_type, duration in type_durations.items():
        if attraction_type in types:
            return duration

    # Check name-based patterns
    name_patterns = {
        "historic": 2.0, "castle": 2.0, "palace": 2.0,
        "cathedral": 1.0, "church": 1.0, "temple": 1.0, "shrine": 1.0,
        "garden": 1.5
    }

    for pattern, duration in name_patterns.items():
        if pattern in name:
            return duration

    # Check for landmarks/monuments
    if "landmark" in types or "monument" in types:
        return 1.0

    # Adjust by popularity
    if rating_count >= 10000:
        return 2.5
    elif rating_count >= 5000:
        return 2.0
    elif rating_count >= 1000:
        return 1.5
    else:
        return 1.0

def is_open_on_date(attraction, date):
    """Check if an attraction is open on a given date."""
    # For now, assume all attractions are open
    # TODO: Implement proper opening hours checking
    return True

async def sort_by_optimal_time_and_proximity(start_location, attractions, current_date):
    """Sort attractions by optimal visiting time and proximity."""
    scored_attractions = []
    current_hour = getattr(current_date, 'hour', 9)
    
    # Score by optimal time
    for attraction in attractions:
        place_id = attraction.get('place_id', 'unknown')
        visit_info = visit_info_cache.get(place_id, {})
        optimal_time = visit_info.get('optimal_time', '').lower()
        
        time_score = 0
        if 'morning' in optimal_time and current_hour < 12:
            time_score = 3
        elif 'afternoon' in optimal_time and 12 <= current_hour < 17:
            time_score = 3
        elif 'evening' in optimal_time and current_hour >= 17:
            time_score = 3
        
        scored_attractions.append((attraction, time_score))
    
    # Group by time score and sort each group by proximity
    grouped = {}
    for attraction, score in scored_attractions:
        if score not in grouped:
            grouped[score] = []
        grouped[score].append(attraction)
    
    result = []
    current = start_location
    
    # Process groups in order of time score
    for score in sorted(grouped.keys(), reverse=True):
        group = grouped[score]
        
        # Sort group by proximity to current location
        while group:
            try:
                distances = gmaps_client.distance_matrix(
                    origins=[current],
                    destinations=[a['geometry']['location'] for a in group[:25]],  # API limit
                    mode="driving",
                    units="metric"
                )
                
                durations = distances["rows"][0]["elements"]
                min_index = min(range(len(durations)), 
                              key=lambda i: durations[i].get("duration", {}).get("value", float('inf')))
                
                nearest = group.pop(min_index)
                result.append(nearest)
                current = nearest['geometry']['location']
                
            except Exception:
                # Fallback: just take first item if API fails
                nearest = group.pop(0)
                result.append(nearest)
                current = nearest['geometry']['location']
    
    return result

async def get_travel_time(origin, destination, mode="driving"):
    """Get travel time between two locations in minutes."""
    try:
        result = gmaps_client.distance_matrix(
            origins=[origin],
            destinations=[destination],
            mode=mode,
            units="metric"
        )
        
        if (result and 
            "rows" in result and 
            len(result["rows"]) > 0 and 
            "elements" in result["rows"][0] and 
            len(result["rows"][0]["elements"]) > 0):
            
            element = result["rows"][0]["elements"][0]
            if element.get("status") == "OK" and "duration" in element:
                return element["duration"]["value"] / 60  # convert to minutes
        
        return 30  # fallback
        
    except Exception:
        return 30  # fallback

async def calculate_distances(origins, destinations, mode="driving"):
    """Calculate distances and travel times between locations."""
    try:
        result = gmaps_client.distance_matrix(
            origins=origins,
            destinations=destinations,
            mode=mode,
            units="metric"
        )
        return result
    except Exception as e:
        return {"error": f"Error calculating distances: {str(e)}"}

# Create the function tools
def create_scheduling_tools(gmaps, gemini_api_key=None):
    """Create scheduling tools with proper client setup."""
    setup_clients(gmaps, gemini_api_key)
    
    schedule_optimizer_tool = FunctionTool(func=optimize_schedule)
    distance_matrix_tool = FunctionTool(func=calculate_distances)
    
    return schedule_optimizer_tool, distance_matrix_tool