# 🎬 Movie Bot

A powerful Telegram bot for movie and TV series distribution with advanced search capabilities, auto-filtering, and file management features.

## ✨ Features

### 🔍 Search & Discovery
- **Smart Search**: Advanced file search with regex pattern matching
- **Inline Search**: Search movies directly from any chat using `@botusername movie_name`
- **Auto Filter**: Automatic responses to movie queries in groups
- **IMDb Integration**: Get detailed movie information with posters and ratings

### 📁 File Management
- **Auto Indexing**: Index files from channels automatically
- **File Auto-Delete**: Files are automatically deleted after a configurable time
- **Duplicate Detection**: Prevents duplicate file storage
- **Format Support**: Supports MP4 and MKV video files

### 👥 Group Management
- **Auto Approval**: Automatically approve chat join requests
- **Service Message Cleanup**: Delete join/leave messages automatically
- **Admin Controls**: Toggle auto-filter on/off per group
- **Force Subscription**: Ensure users join your channel before accessing content

### 🛠️ Owner Features
- **Channel Indexing**: Index entire channels with progress tracking
- **Database Management**: MongoDB integration for file storage
- **Logging**: Comprehensive logging system
- **Statistics**: Track bot usage and file database size
- **Broadcasting**: Send messages to all users and chats

## 🚀 Deployment

### Prerequisites
- Python 3.8+
- MongoDB database
- Telegram Bot Token
- Telegram API credentials

### Environment Variables

Create a `.env` file with the following variables:

```env
# Required
API_ID=your_api_id
API_HASH=your_api_hash
BOT_TOKEN=your_bot_token
MONGO_URL=your_mongodb_connection_string
OWNER_ID=your_telegram_user_id

# Optional
AUTH_CHANNEL=-1001234567890  # Channel ID for force subscription
FSUB=True                    # Enable/disable force subscription
LOGGER_ID=-1001234567890     # Logger group/channel ID
CACHE_TIME=300               # Inline query cache time
FILE_AUTO_DEL_TIMER=600      # File auto-delete timer (seconds)
GROUP_LINK=https://t.me/your_group
COLLECTION_NAME=MyCollection # MongoDB collection name
```

### Installation

#### Local Deployment

1. **Clone the repository**
   ```bash
   git clone https://github.com/MaybeChiku/telegram-movie-bot
   cd telegram-movie-bot
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables**
   ```bash
   cp sample.env .env
   # Edit .env with your credentials
   ```

4. **Run the bot**
   ```bash
   python3 -m src
   ```

#### Docker Deployment

1. **Build and run with Docker**
   ```bash
   docker build -t movie-bot .
   docker run -d --env-file .env movie-bot
   ```

#### Heroku Deployment

1. **Deploy to Heroku**
   ```bash
   git push heroku main
   ```

   The `Procfile` is already configured for Heroku deployment.

## 📋 Commands

### User Commands
- `/start` - Start the bot and get welcome message  
- `/help` - Show help message with available features
- `/search <movie_name>` - Search for movies (groups only)
- `/imdb <movie_name>` - Get IMDb information for a movie
- `/ping` - Check bot response time
- `/autofilter on/off` - Toggle auto-filter in group chats (only for group admins)

### Owner Commands
- `/index` - Index files from a channel
- `/broadcast` - Broadcast message to all users


### Inline Usage
Use `@yourbotusername movie_name` in any chat to search for movies inline.


## 🔧 Configuration

### MongoDB Setup
The bot uses MongoDB for storing:
- File metadata (name, size, file_id, etc.)
- User and chat information
- Auto-filter settings

### Channel Indexing
To index a channel:
1. Forward the last message from the channel to the bot
2. Use `/index` command as owner
3. Follow the prompts to start indexing

### Force Subscription
Set `AUTH_CHANNEL` to your channel ID to force users to join before accessing content.

## 🛡️ Security Features

- **Owner-only commands**: Critical commands restricted to bot owner
- **Admin verification**: Group admin verification for sensitive operations  
- **Force subscription**: Ensure users join your channel
- **Input validation**: Proper validation of user inputs
- **Error handling**: Comprehensive error handling and logging

## 📊 Database Schema

### Files Collection
```javascript
{
  file_id: String,      // Unique file identifier
  file_ref: String,     // File reference
  file_name: String,    // Original file name
  file_size: Number,    // File size in bytes
  mime_type: String,    // MIME type
  caption: String,      // File caption
  file_type: String     // File type (video/document)
}
```
## 🤝 Contributing

Contributions are welcome! Please fork the repository, create a feature branch for your changes, test thoroughly, and submit a pull request.

## 📝 License

This project is open source. Feel free to use, modify, and distribute according to your needs.

## 🛠️ Bug Reports & Support

- **Issues**: Report bugs via GitHub Issues
- **Feature Requests**: Suggest new features in Issues
- **Support**: Join our [Support Group](https://t.me/DebugAngels)

## 🎉 Acknowledgments

- Built with [pyrofork](https://github.com/pyrofork/pyrofork) – A modern fork of the Pyrogram Telegram Bot API framework
- Database powered by [MongoDB](https://www.mongodb.com/)
- Deployed on [Heroku](https://www.heroku.com/) and [Docker](https://www.docker.com/)

## ⚠️ Disclaimer

This bot is for educational purposes only. Users are responsible for ensuring they comply with copyright laws and Telegram's Terms of Service when using this bot.
