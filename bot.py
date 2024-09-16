import tweepy
from googleapiclient.discovery import build
from config import TWITTER_CONSUMER_KEY, TWITTER_CONSUMER_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET, YOUTUBE_API_KEY, BEARER_TOKEN
import json
import os
import time
import spacy

# Initialize spaCy for NLP
nlp = spacy.load('en_core_web_sm')

# Initialize YouTube API client
youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)

# File to store historical video data
HISTORICAL_DATA_FILE = 'historical_video_data.json'
# File to store posted tweets
POSTED_TWEETS_FILE = 'posted_tweets.json'

# Load historical video data from file
def load_historical_data():
    if os.path.exists(HISTORICAL_DATA_FILE):
        with open(HISTORICAL_DATA_FILE, 'r') as f:
            return json.load(f)
    return {}

# Save historical video data to file
def save_historical_data(data):
    with open(HISTORICAL_DATA_FILE, 'w') as f:
        json.dump(data, f)

# Load posted tweets data from file
def load_posted_tweets():
    if os.path.exists(POSTED_TWEETS_FILE):
        with open(POSTED_TWEETS_FILE, 'r') as f:
            return set(json.load(f))
    return set()

# Save posted tweets data to file
def save_posted_tweets(tweets):
    with open(POSTED_TWEETS_FILE, 'w') as f:
        json.dump(list(tweets), f)

# Function to format view count
def format_view_count(view_count):
    return "{:,}".format(int(view_count)).replace(',', '.')

# NLP-based function to extract keywords and entities for dynamic hashtags
def extract_keywords_for_hashtags(title, description):
    hashtags = []
    text = f"{title} {description}"
    doc = nlp(text)
    
    # Extract entities like PERSON, ORG, etc.
    for ent in doc.ents:
        if ent.label_ in ['PERSON', 'ORG', 'WORK_OF_ART', 'EVENT']:
            hashtags.append(f"#{ent.text.replace(' ', '')}")
    
    # Extract nouns for potential keywords
    for token in doc:
        if token.pos_ in ['NOUN', 'PROPN'] and not token.is_stop and len(token.text) > 3:
            hashtags.append(f"#{token.text.replace(' ', '')}")
    
    return hashtags

# Define a mapping of keywords to hashtags
def get_relevant_hashtags(title, description):
    # Static predefined hashtags
    hashtags = ['#trending', '#Turkey', '#USA', '#YouTube', '#viral', '#video']
    
    # Extract dynamic hashtags using NLP
    dynamic_hashtags = extract_keywords_for_hashtags(title, description)
    
    # Extend static hashtags with dynamic ones
    hashtags.extend(dynamic_hashtags)
    
    return list(set(hashtags))  # Remove duplicates

# General hashtags to be added to each tweet
def get_general_hashtags():
    return ['#trending', '#Turkey', '#USA', '#YouTube', '#viral', '#video']

# Function to get trending videos for a specific region
def get_trending_videos(region_code='TR', max_results=5):
    request = youtube.videos().list(
        part="snippet,statistics",
        chart="mostPopular",
        regionCode=region_code,
        maxResults=max_results
    )
    response = request.execute()

    trending_videos = []
    for item in response.get('items', []):
        video_id = item['id']
        title = item['snippet']['title']
        description = item['snippet']['description']
        url = f"https://www.youtube.com/watch?v={video_id}"
        view_count = item['statistics']['viewCount']
        formatted_view_count = format_view_count(view_count)
        hashtags = get_relevant_hashtags(title, description)  # Get relevant hashtags
        trending_videos.append({
            'title': title,
            'description': description,
            'url': url,
            'view_count': view_count,
            'view_count_formatted': formatted_view_count,
            'hashtags': ' '.join(hashtags),
            'video_id': video_id,
            'region': region_code
        })
    
    return trending_videos

# Fetch trending videos for Turkey and USA
def fetch_all_trending_videos():
    regions = {
        'TR': 'Türkiye',
        'US': 'ABD'
    }

    all_videos = []
    video_ids = set()  # Track video IDs to avoid duplicates

    # Fetch and store trending videos by region
    for region_code, region_name in regions.items():
        trending_videos = get_trending_videos(region_code)
        for video in trending_videos:
            if video['video_id'] not in video_ids:
                video['region'] = region_name
                all_videos.append(video)
                video_ids.add(video['video_id'])
    
    return all_videos

# Filter videos with significant view count increase
def filter_most_viewed_videos(current_videos, historical_data):
    filtered_videos = []
    
    for video in current_videos:
        video_id = video['video_id']
        current_view_count = int(video['view_count'])

        # Check if video data exists in historical data
        if video_id in historical_data:
            previous_view_count = int(historical_data[video_id]['view_count'])
            view_count_increase = current_view_count - previous_view_count
            
            # Add video to the list if it has a significant increase
            if view_count_increase > 10000:  # You can adjust the threshold as needed
                filtered_videos.append(video)
        else:
            # Add video to the list if it's new
            filtered_videos.append(video)

        # Update historical data with current view count
        historical_data[video_id] = {'view_count': video['view_count']}

    # Save updated historical data
    save_historical_data(historical_data)

    return filtered_videos

# Initialize Twitter API client using OAuth 2.0 Bearer Token
client = tweepy.Client(bearer_token=BEARER_TOKEN, 
                       consumer_key=TWITTER_CONSUMER_KEY,
                       consumer_secret=TWITTER_CONSUMER_SECRET,
                       access_token=TWITTER_ACCESS_TOKEN,
                       access_token_secret=TWITTER_ACCESS_SECRET)

# Function to post the trending video on Twitter with relevant and general hashtags
def post_trending_videos(videos, posted_tweets):
    # Only post the top 3 videos per region
    regions = {'Türkiye': [], 'ABD': []}
    
    for video in videos:
        region_name = video['region']
        if len(regions[region_name]) < 3:
            tweet_text = (f"🔥 YouTube'da Trend: {video['title']}\n"
                          f"📍 Trend Ülke: {video['region']}\n"
                          f"👀 İzle: {video['url']}\n"
                          f"👁️ Görüntülenme: {video['view_count_formatted']}\n"
                          f"{video['hashtags']}")

            # Check if the tweet has already been posted
            if tweet_text not in posted_tweets:
                try:
                    response = client.create_tweet(text=tweet_text)
                    print("Tweet posted successfully!", response.data)
                    posted_tweets.add(tweet_text)
                    save_posted_tweets(posted_tweets)  # Update posted tweets data
                except tweepy.TooManyRequests as e:
                    print("Rate limit exceeded, retrying...")
                    time.sleep(15 * 60)  # Wait for 15 minutes before retrying
                except tweepy.TweepyException as e:
                    print(f"Error posting tweet: {e}")

            regions[region_name].append(video)

# Main function to fetch and post trending videos manually
def main():
    historical_data = load_historical_data()
    posted_tweets = load_posted_tweets()

    trending_videos = fetch_all_trending_videos()
    most_viewed_videos = filter_most_viewed_videos(trending_videos, historical_data)
    post_trending_videos(most_viewed_videos, posted_tweets)

if __name__ == "__main__":
    main()
