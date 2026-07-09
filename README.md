# ZitCoin Discord Bot v. 1.0

ZitCoin is a Discord bot that manages a server economy backed by MySQL.
It provides registration, balances, transfers, requests, loans, admin tooling, and interactive GUI panels.

## Features

- User registration and unlinking with role assignment support
- Currency conversion helpers
- Balance tracking and user-to-user transfers
- Withdrawal, deposit, and loan requests
- Admin approval and denial workflow for requests
- Loan management and user/account admin commands
- Interactive user and admin banking panels
- Channel-based quick access panel via the zca command

## Project Structure

- main.py: Bot startup, intents, cog loading, and slash command sync
- financeDatabase.py: MySQL connection and all data access classes
- migrate_to_mysql.py: One-shot table bootstrap/migration initializer
- cogs/banking.py: Banking, transfer, request, and loan logic
- cogs/others.py: Registration, utility commands, and the ZCA button panel
- a.env: Environment configuration file loaded at startup

## Requirements

- Python 3.10+
- MySQL server
- Discord bot token

Python packages used:

- discord.py
- python-dotenv
- mysql-connector-python

## Environment Variables

The bot loads environment variables from a.env.

Required:

- DISCORD_TOKEN
- MYSQL_USER
- MYSQL_PASSWORD
- MYSQL_PORT
- MYSQL_DATABASE
- WITHDRAWAL_REQUESTS_CHANNEL_ID
- DEPOSIT_REQUESTS_CHANNEL_ID
- LOAN_REQUESTS_CHANNEL_ID
- TRANSACTIONS_LOGS_CHANNEL_ID
- ZITCOIN_MEMBER_ROLE_ID

Example (IDs can vary): 

	DISCORD_TOKEN=your_discord_bot_token
	MYSQL_USER=your_mysql_user
	MYSQL_PASSWORD=your_mysql_password
	MYSQL_HOST=localhost
	MYSQL_PORT=3306
	MYSQL_DATABASE=zitcoin
	WITHDRAWAL_REQUESTS_CHANNEL_ID=1523049697948733522
	DEPOSIT_REQUESTS_CHANNEL_ID=1523049675484037282
	LOAN_REQUESTS_CHANNEL_ID=1523049754681151688
	TRANSACTIONS_LOGS_CHANNEL_ID=1523049492121784550
	ZITCOIN_MEMBER_ROLE_ID=1523049840995733524

## Setup

1. Create and activate a virtual environment.
2. Install dependencies.
3. Fill a.env with your values.
4. Initialize database tables.
5. Run the bot.

Example commands:

	python3 -m venv myenv
	source myenv/bin/activate
	pip install discord.py python-dotenv mysql-connector-python OR pip install -r requirements.txt
	python3 migrate_to_mysql.py
	python3 main.py

## Database Schema

The bot auto-creates these tables:

### users

- discord_id BIGINT PRIMARY KEY
- mc_username VARCHAR(255)
- balance DOUBLE DEFAULT 0

### loans

- discord_id BIGINT PRIMARY KEY
- amount DOUBLE
- interest_rate DOUBLE
- due_date VARCHAR(255)

### requests

- request_id INT AUTO_INCREMENT PRIMARY KEY
- discord_id BIGINT
- request_type VARCHAR(255)
- status VARCHAR(255)
- created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

### transactions

- transaction_id INT AUTO_INCREMENT PRIMARY KEY
- discord_id BIGINT
- amount DOUBLE
- transaction_type VARCHAR(255)
- created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

## Command Reference

Most commands are slash-accessible. Hybrid commands are also defined, but with command_prefix=None the bot is operated as slash-first.

### Panels

<img width="656" height="218" alt="image" src="https://github.com/user-attachments/assets/c5ddb814-ee5b-4cbb-ae3d-4f83f2273f1d" />
<img width="656" height="218" alt="image" src="https://github.com/user-attachments/assets/54a4845f-40bc-4da2-90cb-04c57aecaa5d" />



- /zitcoin: Opens user banking dropdown panel
- /zitcoin_admin: Opens admin banking dropdown panel (admin only)
- /zca: Posts channel embed with Register, Unregister, and Start Banking buttons (admin only)

### User Commands

- /register <mc_username>
- /unregister
- /ping
- /convert <amount> <from_currency> <to_currency>
- /cmds
- /balance
- /transfer <mc_username> <amount>
- /request_withdrawal <amount>
- /request_deposit <amount>
- /request_loan <amount>

### Admin Commands

- /exchange_info
- /registration_info
- /remove_user <mc_username>
- /approve_request <request_id>
- /deny_request <request_id>
- /request_approve <request_id>
- /request_deny <request_id>
- /get_all_requests
- /get_request_by_id <request_id>
- /get_requests_by_status <status>
- /get_requests_by_discord_id <discord_id>
- /set_balance <mc_username> <new_balance>
- /add_balance <mc_username> <amount>
- /remove_balance <mc_username> <amount>
- /loan <mc_username> <amount> <due_date>
- /get_loan <mc_username>
- /get_all_loans
- /remove_loan <mc_username>
- /get_user <mc_username>
- /get_user_by_discord_id <discord_id>
- /get_all_users

## ZCA Channel GUI

The zca panel is designed to be posted in your ZitCoin channel.

<img width="773" height="361" alt="image" src="https://github.com/user-attachments/assets/8c104aba-88a8-4ed4-89db-c75d2382e963" />


Buttons:

- Register: Opens a modal for Minecraft username and registers the user
- Unregister: Removes existing registration
- Start Banking: Opens the same personal banking panel as /zitcoin

Behavior notes:

- Register and Unregister responses are ephemeral to the clicker
- Start Banking opens an ephemeral personal panel
- The view is registered as persistent at startup in cogs/others.py

## Interest Model

Loan interest tiers used by banking logic:

- 1 to 9 ZitCoin: 20%
- 10 to 32 ZitCoin: 10%
- 33 to 64 ZitCoin: 7.5%
- Above 64 ZitCoin: 5%

## Channel IDs and Role ID

This project reads Discord channel and role IDs from environment variables in a.env.

If you deploy to another server, update these variables:

- WITHDRAWAL_REQUESTS_CHANNEL_ID
- DEPOSIT_REQUESTS_CHANNEL_ID
- LOAN_REQUESTS_CHANNEL_ID
- TRANSACTIONS_LOGS_CHANNEL_ID
- ZITCOIN_MEMBER_ROLE_ID

## Startup Flow

1. main.py loads a.env
2. Bot starts with required intents
3. Cogs are loaded from cogs/banking.py and cogs/others.py
4. Slash commands are synced in on_ready

## Troubleshooting

### Slash command does not appear

- Confirm bot is running and on_ready has executed
- Ensure the bot has applications.commands scope in your server
- Restart bot to force sync cycle

### Unexpected Error on request approval or denial

- Run python3 migrate_to_mysql.py to ensure request table shape is up to date
- Restart the bot after migration

### MySQL connection fails

- Verify MYSQL_USER and MYSQL_PASSWORD in a.env
- Ensure MYSQL_HOST and MYSQL_PORT are reachable
- Confirm database user permissions allow CREATE, SELECT, INSERT, UPDATE, DELETE

### Role not assigned on register

- Verify role ID configured in cogs/others.py
- Ensure bot role is above target role in server role hierarchy
- Ensure bot has Manage Roles permission

## Maintenance

- Re-run python3 migrate_to_mysql.py after schema-related changes
- Keep dependencies updated in your environment
- Consider adding a requirements.txt for reproducible installs

## Security Notes

- Never commit real tokens or database passwords
- Restrict admin commands to trusted roles only
- Rotate credentials if exposed
