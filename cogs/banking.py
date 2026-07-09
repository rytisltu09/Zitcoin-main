from datetime import datetime, timezone
import os

import discord
from discord import app_commands
from discord.ext import commands

from financeDatabase import BankDB, FinanceDB, RequestsDB, TransactionsDB


def format_discord_timestamp(value):
    if hasattr(value, "timestamp"):
        if value.tzinfo is None:
            local_tz = datetime.now().astimezone().tzinfo or timezone.utc
            value = value.replace(tzinfo=local_tz)
        unix_ts = int(value.timestamp())
        return f"<t:{unix_ts}:F> (<t:{unix_ts}:R>)"
    return str(value)


def _env_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError:
        return default


class BankingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.palette = {
            "primary": 0x2D5B87,
            "success": 0x2E8B57,
            "warning": 0xD28B26,
            "error": 0xB03A48,
            "info": 0x3F6D63,
            "muted": 0x4A5261,
        }
        self.zitcoin_to_diamonds_rate = 2
        self.diamonds_to_zitcoin_rate = 1 / self.zitcoin_to_diamonds_rate

        self.zitcoins_1_9_interest_rate = 0.2
        self.zitcoins_10_32_interest_rate = 0.1
        self.zitcoins_32_64_interest_rate = 0.075
        self.zitcoins_above_64_interest_rate = 0.05

        self.withdrawal_requests_channel_id = _env_int("WITHDRAWAL_REQUESTS_CHANNEL_ID", 0)
        self.deposit_requests_channel_id = _env_int("DEPOSIT_REQUESTS_CHANNEL_ID", 0)
        self.loan_requests_channel_id = _env_int("LOAN_REQUESTS_CHANNEL_ID", 0)
        self.transactions_logs_channel_id = _env_int("TRANSACTIONS_LOGS_CHANNEL_ID", 0)

    def _build_embed(self, title: str, description: str, tone: str = "primary") -> discord.Embed:
        embed = discord.Embed(
            title=title,
            description=description,
            color=self.palette.get(tone, self.palette["primary"]),
            timestamp=datetime.now(timezone.utc),
        )
        return embed

    def _to_float(self, value, default: float = 0.0) -> float:
        try:
            if value is None:
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    def _format_request_line(self, request_row) -> str:
        request_id = request_row[0] if len(request_row) > 0 else "?"
        discord_id = request_row[1] if len(request_row) > 1 else 0
        request_type = request_row[2] if len(request_row) > 2 else "unknown"
        status = request_row[3] if len(request_row) > 3 else "unknown"
        created_at = request_row[4] if len(request_row) > 4 else "unknown"
        return (
            f"• ID {request_id} | {self._discord_user_label(int(discord_id))} | "
            f"{request_type} | {status} | {format_discord_timestamp(created_at)}"
        )

    async def _send_embed(self, ctx: commands.Context, title: str, description: str, tone: str = "primary"):
        await ctx.send(embed=self._build_embed(title, description, tone))

    async def _send_error(self, ctx: commands.Context):
        await self._send_embed(ctx, "Unexpected Error", "Something went wrong while processing this command.", "error")

    def _discord_user_label(self, discord_id: int) -> str:
        user = self.bot.get_user(discord_id)
        return str(user) if user else f"Unknown User (ID: {discord_id})"

    async def _send_lines_as_embeds(self, ctx: commands.Context, title: str, lines: list[str], tone: str = "primary"):
        if not lines:
            await self._send_embed(ctx, title, "No records found.", "warning")
            return

        chunk_size = 12
        total_pages = (len(lines) + chunk_size - 1) // chunk_size
        for page, start in enumerate(range(0, len(lines), chunk_size), start=1):
            page_lines = lines[start : start + chunk_size]
            embed = self._build_embed(title, "\n".join(page_lines), tone)
            if total_pages > 1:
                embed.set_footer(text=f"Page {page}/{total_pages}")
            await ctx.send(embed=embed)

    async def _send_interaction_embed(self, interaction: discord.Interaction, embed: discord.Embed, ephemeral: bool = True):
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=ephemeral)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=ephemeral)

    async def _send_interaction_text(self, interaction: discord.Interaction, title: str, description: str, tone: str = "primary", ephemeral: bool = True):
        await self._send_interaction_embed(interaction, self._build_embed(title, description, tone), ephemeral)

    async def _send_interaction_lines(self, interaction: discord.Interaction, title: str, lines: list[str], tone: str = "primary", ephemeral: bool = True):
        if not lines:
            await self._send_interaction_text(interaction, title, "No records found.", "warning", ephemeral)
            return

        chunk_size = 12
        chunks = [lines[i : i + chunk_size] for i in range(0, len(lines), chunk_size)]
        first_embed = self._build_embed(title, "\n".join(chunks[0]), tone)
        if len(chunks) > 1:
            first_embed.set_footer(text=f"Page 1/{len(chunks)}")
        await self._send_interaction_embed(interaction, first_embed, ephemeral)

        for page, page_lines in enumerate(chunks[1:], start=2):
            page_embed = self._build_embed(title, "\n".join(page_lines), tone)
            page_embed.set_footer(text=f"Page {page}/{len(chunks)}")
            await interaction.followup.send(embed=page_embed, ephemeral=ephemeral)

    def _calculate_interest_rate(self, amount: float) -> float:
        if amount <= 9:
            return self.zitcoins_1_9_interest_rate
        if amount <= 32:
            return self.zitcoins_10_32_interest_rate
        if amount <= 64:
            return self.zitcoins_32_64_interest_rate
        return self.zitcoins_above_64_interest_rate

    @app_commands.command(name="zitcoin", description="Open the ZitCoin user command panel.")
    async def zitcoin(self, interaction: discord.Interaction):
        embed = self._build_embed(
            "ZitCoin User Panel",
            "Pick an action from the dropdown below to manage your account.",
            "primary",
        )
        await interaction.response.send_message(embed=embed, view=ZitcoinUserView(self, interaction.user.id), ephemeral=True)

    @app_commands.command(name="zitcoin_admin", description="Open the ZitCoin admin command panel.")
    @app_commands.default_permissions(administrator=True)
    async def zitcoin_admin(self, interaction: discord.Interaction):
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if not member or not member.guild_permissions.administrator:
            await self._send_interaction_text(interaction, "Permission Denied", "You must be an administrator to use this panel.", "error")
            return

        embed = self._build_embed(
            "ZitCoin Admin Panel",
            "Pick an admin action from the dropdown below.",
            "muted",
        )
        await interaction.response.send_message(embed=embed, view=ZitcoinAdminView(self, interaction.user.id), ephemeral=True)

    async def ui_user_balance(self, interaction: discord.Interaction):
        try:
            db = FinanceDB()
            discord_id = interaction.user.id
            if not db.user_exists(discord_id):
                await self._send_interaction_text(
                    interaction,
                    "Registration Required",
                    "You are not registered. Use /register <mc_username> first.",
                    "warning",
                )
                return

            balance = self._to_float(db.get_balance(discord_id))
            diamonds_value = balance * self.diamonds_to_zitcoin_rate
            embed = self._build_embed("Account Balance", "Your current wallet snapshot:", "info")
            embed.add_field(name="ZitCoin", value=f"{balance} Z$", inline=True)
            embed.add_field(name="Diamond Equivalent", value=f"{diamonds_value} diamonds", inline=True)
            await self._send_interaction_embed(interaction, embed)
        except Exception as exc:
            print(f"ui_user_balance error for user {interaction.user.id}: {exc}")
            await self._send_interaction_text(interaction, "Unexpected Error", "Something went wrong while processing this action.", "error")

    async def ui_user_request(self, interaction: discord.Interaction, request_type: str, amount: float):
        try:
            channel_map = {
                "withdrawal": self.withdrawal_requests_channel_id,
                "deposit": self.deposit_requests_channel_id,
                "loan": self.loan_requests_channel_id,
            }
            tone_map = {"withdrawal": "warning", "deposit": "info", "loan": "primary"}
            db_finance = FinanceDB()
            db_requests = RequestsDB()
            discord_id = interaction.user.id

            if not db_finance.user_exists(discord_id):
                await self._send_interaction_text(
                    interaction,
                    "Registration Required",
                    "You are not registered. Use /register <mc_username> first.",
                    "warning",
                )
                return

            if amount <= 0:
                await self._send_interaction_text(interaction, "Invalid Amount", "Amount must be greater than zero.", "warning")
                return

            if request_type == "withdrawal":
                current_balance = db_finance.get_balance(discord_id)
                if current_balance < amount:
                    await self._send_interaction_text(
                        interaction,
                        "Insufficient Funds",
                        "You do not have enough balance for this withdrawal.",
                        "warning",
                    )
                    return

            db_requests.add_request(discord_id, request_type, "pending")
            await self._send_interaction_text(
                interaction,
                "Request Submitted",
                f"Your {request_type} request for {amount}Z$ has been submitted.",
                "success",
            )

            request_channel = self.bot.get_channel(channel_map[request_type])
            if request_channel:
                logs = self._build_embed(
                    f"{request_type.capitalize()} Request",
                    "A new request is pending review.",
                    tone_map[request_type],
                )
                logs.add_field(name="User", value=f"{interaction.user} (ID: {discord_id})")
                logs.add_field(name="Amount", value=f"{amount}Z$")
                await request_channel.send(embed=logs)
        except Exception:
            await self._send_interaction_text(interaction, "Unexpected Error", "Something went wrong while processing this action.", "error")

    async def ui_user_transfer(self, interaction: discord.Interaction, mc_username: str, amount: float):
        try:
            if amount <= 0:
                await self._send_interaction_text(interaction, "Invalid Amount", "Transfer amount must be greater than zero.", "warning")
                return

            transactions_logs = self.bot.get_channel(self.transactions_logs_channel_id)
            db = FinanceDB()
            db_transactions = TransactionsDB()
            sender_discord_id = interaction.user.id
            if not db.user_exists(sender_discord_id):
                await self._send_interaction_text(
                    interaction,
                    "Registration Required",
                    "You are not registered. Use /register <mc_username> first.",
                    "warning",
                )
                return

            sender_balance = self._to_float(db.get_balance(sender_discord_id))
            if sender_balance < amount:
                await self._send_interaction_text(interaction, "Insufficient Funds", "You do not have enough balance for this transfer.", "warning")
                return

            recipient = db.get_user_by_mc_username(mc_username)
            if not recipient:
                await self._send_interaction_text(interaction, "Recipient Not Found", "Recipient user was not found.", "warning")
                return

            if len(recipient) < 3:
                await self._send_interaction_text(
                    interaction,
                    "Database Schema Issue",
                    "Your users table is missing required columns. Run migrate_to_mysql.py and restart the bot.",
                    "error",
                )
                return

            recipient_discord_id, _, recipient_balance = recipient
            if recipient_discord_id == sender_discord_id:
                await self._send_interaction_text(interaction, "Invalid Recipient", "You cannot transfer ZitCoin to yourself.", "warning")
                return

            recipient_balance = self._to_float(recipient_balance)
            new_sender_balance = sender_balance - amount
            new_recipient_balance = recipient_balance + amount

            db.cursor.execute("UPDATE users SET balance = %s WHERE discord_id = %s", (new_sender_balance, sender_discord_id))
            db.cursor.execute("UPDATE users SET balance = %s WHERE discord_id = %s", (new_recipient_balance, recipient_discord_id))
            db.conn.commit()

            db_transactions.add_transaction(sender_discord_id, amount, "transfer")

            embed = self._build_embed("Transfer Complete", "Funds moved successfully.", "success")
            embed.add_field(name="Recipient", value=mc_username, inline=True)
            embed.add_field(name="Amount", value=f"{amount}Z$", inline=True)
            embed.add_field(name="New Balance", value=f"{new_sender_balance}Z$", inline=False)
            await self._send_interaction_embed(interaction, embed)

            if transactions_logs:
                logs = self._build_embed("Transaction Event", "Transfer recorded in the ledger.", "muted")
                logs.add_field(name="Sender ID", value=f"{sender_discord_id}")
                logs.add_field(name="Receiver ID", value=f"{recipient_discord_id}")
                logs.add_field(name="Amount", value=f"{amount}Z$")
                await transactions_logs.send(embed=logs)
        except Exception as exc:
            print(f"ui_user_transfer error for user {interaction.user.id}: {exc}")
            await self._send_interaction_text(interaction, "Unexpected Error", "Something went wrong while processing this action.", "error")

    async def ui_admin_approve_request(self, interaction: discord.Interaction, request_id: int):
        try:
            db_requests = RequestsDB()
            request = db_requests.get_request(request_id)
            if not request:
                await self._send_interaction_text(interaction, "Request Not Found", "No request exists with that ID.", "warning")
                return

            _, _, _, status, _ = request
            if status != "pending":
                await self._send_interaction_text(interaction, "Request Already Processed", "This request has already been processed.", "warning")
                return

            db_requests.update_request_status(request_id, "approved")
            await self._send_interaction_text(interaction, "Request Approved", f"Request ID {request_id} has been approved.", "success")
        except Exception:
            await self._send_interaction_text(interaction, "Unexpected Error", "Something went wrong while processing this action.", "error")

    async def ui_admin_deny_request(self, interaction: discord.Interaction, request_id: int):
        try:
            db_requests = RequestsDB()
            request = db_requests.get_request(request_id)
            if not request:
                await self._send_interaction_text(interaction, "Request Not Found", "No request exists with that ID.", "warning")
                return

            _, _, _, status, _ = request
            if status != "pending":
                await self._send_interaction_text(interaction, "Request Already Processed", "This request has already been processed.", "warning")
                return

            db_requests.update_request_status(request_id, "denied")
            await self._send_interaction_text(interaction, "Request Denied", f"Request ID {request_id} has been denied.", "error")
        except Exception:
            await self._send_interaction_text(interaction, "Unexpected Error", "Something went wrong while processing this action.", "error")

    async def ui_admin_set_balance(self, interaction: discord.Interaction, mc_username: str, amount: float):
        try:
            db = FinanceDB()
            user = db.get_user_by_mc_username(mc_username)
            if not user:
                await self._send_interaction_text(interaction, "User Not Found", "No user exists with that Minecraft username.", "warning")
                return

            discord_id, _, _ = user
            db.cursor.execute("UPDATE users SET balance = %s WHERE discord_id = %s", (amount, discord_id))
            db.conn.commit()
            await self._send_interaction_text(interaction, "Balance Updated", f"Balance for {mc_username} has been updated to {amount}Z$.", "success")
        except Exception:
            await self._send_interaction_text(interaction, "Unexpected Error", "Something went wrong while processing this action.", "error")

    async def ui_admin_add_balance(self, interaction: discord.Interaction, mc_username: str, amount: float):
        try:
            if amount <= 0:
                await self._send_interaction_text(interaction, "Invalid Amount", "Amount must be greater than zero.", "warning")
                return

            db = FinanceDB()
            user = db.get_user_by_mc_username(mc_username)
            if not user:
                await self._send_interaction_text(interaction, "User Not Found", "No user exists with that Minecraft username.", "warning")
                return

            discord_id, _, balance = user
            new_balance = self._to_float(balance) + amount
            db.cursor.execute("UPDATE users SET balance = %s WHERE discord_id = %s", (new_balance, discord_id))
            db.conn.commit()
            await self._send_interaction_text(
                interaction,
                "Balance Added",
                f"Added {amount}Z$ to {mc_username}'s balance. New balance is {new_balance}Z$.",
                "success",
            )
        except Exception as exc:
            print(f"ui_admin_add_balance error: {exc}")
            await self._send_interaction_text(interaction, "Unexpected Error", "Something went wrong while processing this action.", "error")

    async def ui_admin_remove_balance(self, interaction: discord.Interaction, mc_username: str, amount: float):
        try:
            if amount <= 0:
                await self._send_interaction_text(interaction, "Invalid Amount", "Amount must be greater than zero.", "warning")
                return

            db = FinanceDB()
            user = db.get_user_by_mc_username(mc_username)
            if not user:
                await self._send_interaction_text(interaction, "User Not Found", "No user exists with that Minecraft username.", "warning")
                return

            discord_id, _, balance = user
            new_balance = self._to_float(balance) - amount
            if new_balance < 0:
                await self._send_interaction_text(interaction, "Insufficient Funds", "Cannot remove more than the user's current balance.", "warning")
                return

            db.cursor.execute("UPDATE users SET balance = %s WHERE discord_id = %s", (new_balance, discord_id))
            db.conn.commit()
            await self._send_interaction_text(
                interaction,
                "Balance Removed",
                f"Removed {amount}Z$ from {mc_username}'s balance. New balance is {new_balance}Z$.",
                "success",
            )
        except Exception as exc:
            print(f"ui_admin_remove_balance error: {exc}")
            await self._send_interaction_text(interaction, "Unexpected Error", "Something went wrong while processing this action.", "error")

    async def ui_admin_get_all_requests(self, interaction: discord.Interaction):
        try:
            db_requests = RequestsDB()
            requests = db_requests.get_all_requests()
            request_lines = [self._format_request_line(request_row) for request_row in requests]
            await self._send_interaction_lines(interaction, "All Requests", request_lines, "info")
        except Exception as exc:
            print(f"ui_admin_get_all_requests error: {exc}")
            await self._send_interaction_text(interaction, "Unexpected Error", "Something went wrong while processing this action.", "error")

    async def ui_admin_get_all_users(self, interaction: discord.Interaction):
        try:
            db = FinanceDB()
            users = db.get_all_users()
            user_lines = [
                f"• {self._discord_user_label(discord_id)} | {mc_username} | {balance}Z$"
                for discord_id, mc_username, balance in users
            ]
            await self._send_interaction_lines(interaction, "All Users", user_lines, "info")
        except Exception:
            await self._send_interaction_text(interaction, "Unexpected Error", "Something went wrong while processing this action.", "error")

    async def ui_admin_get_all_loans(self, interaction: discord.Interaction):
        try:
            db = BankDB()
            loans = db.get_all_loans()
            loan_lines = [
                f"• {self._discord_user_label(discord_id)} | {amount}Z$ | {interest_rate * 100}% | due {due_date}"
                for discord_id, amount, interest_rate, due_date in loans
            ]
            await self._send_interaction_lines(interaction, "All Loans", loan_lines, "info")
        except Exception:
            await self._send_interaction_text(interaction, "Unexpected Error", "Something went wrong while processing this action.", "error")

    async def ui_admin_create_loan(self, interaction: discord.Interaction, mc_username: str, amount: float, due_date: str):
        try:
            if amount <= 0:
                await self._send_interaction_text(interaction, "Invalid Amount", "Loan amount must be greater than zero.", "warning")
                return

            db_users = FinanceDB()
            db_loans = BankDB()
            user = db_users.get_user_by_mc_username(mc_username)
            if not user:
                await self._send_interaction_text(interaction, "User Not Found", "No user exists with that Minecraft username.", "warning")
                return

            discord_id, _, balance = user
            if db_loans.get_loan(discord_id):
                await self._send_interaction_text(interaction, "Loan Exists", f"{mc_username} already has an active loan.", "warning")
                return

            interest_rate = self._calculate_interest_rate(amount)
            db_loans.add_loan(discord_id, amount, interest_rate, due_date)

            new_balance = self._to_float(balance) + amount
            db_users.cursor.execute("UPDATE users SET balance = %s WHERE discord_id = %s", (new_balance, discord_id))
            db_users.conn.commit()

            total_repayment = amount * (1 + interest_rate)
            embed = self._build_embed("Loan Created", "A loan has been issued.", "success")
            embed.add_field(name="User", value=mc_username, inline=True)
            embed.add_field(name="Amount", value=f"{amount}Z$", inline=True)
            embed.add_field(name="Interest", value=f"{interest_rate * 100}%", inline=True)
            embed.add_field(name="Total Repayment", value=f"{total_repayment}Z$", inline=True)
            embed.add_field(name="New Balance", value=f"{new_balance}Z$", inline=True)
            embed.add_field(name="Due Date", value=due_date, inline=False)
            await self._send_interaction_embed(interaction, embed)
        except Exception as exc:
            print(f"ui_admin_create_loan error: {exc}")
            await self._send_interaction_text(interaction, "Unexpected Error", "Something went wrong while processing this action.", "error")

    async def ui_admin_remove_loan(self, interaction: discord.Interaction, mc_username: str):
        try:
            db_users = FinanceDB()
            db_loans = BankDB()
            user = db_users.get_user_by_mc_username(mc_username)
            if not user:
                await self._send_interaction_text(interaction, "User Not Found", "No user exists with that Minecraft username.", "warning")
                return

            discord_id, _, _ = user
            loan = db_loans.get_loan(discord_id)
            if not loan:
                await self._send_interaction_text(interaction, "Loan Not Found", f"No loan found for {mc_username}.", "warning")
                return

            db_loans.remove_loan(discord_id)
            await self._send_interaction_text(interaction, "Loan Removed", f"Loan for {mc_username} has been removed.", "success")
        except Exception:
            await self._send_interaction_text(interaction, "Unexpected Error", "Something went wrong while processing this action.", "error")

    @commands.hybrid_command()
    async def balance(self, ctx: commands.Context):
        try:
            db = FinanceDB()
            discord_id = ctx.author.id
            if db.user_exists(discord_id):
                balance = self._to_float(db.get_balance(discord_id))
                diamonds_value = balance * self.diamonds_to_zitcoin_rate
                embed = self._build_embed("Account Balance", "Your current wallet snapshot:", "info")
                embed.add_field(name="ZitCoin", value=f"{balance} Z$", inline=True)
                embed.add_field(name="Diamond Equivalent", value=f"{diamonds_value} diamonds", inline=True)
                await ctx.send(embed=embed)
            else:
                await self._send_embed(
                    ctx,
                    "Registration Required",
                    "You are not registered. Use /register <mc_username> first.",
                    "warning",
                )
        except Exception:
            await self._send_error(ctx)

    @commands.hybrid_command()
    async def request_withdrawal(self, ctx: commands.Context, amount: float):
        try:
            withdrawal_requests_channel = self.bot.get_channel(self.withdrawal_requests_channel_id)
            db_finance = FinanceDB()
            db_requests = RequestsDB()
            discord_id = ctx.author.id
            if not db_finance.user_exists(discord_id):
                await self._send_embed(
                    ctx,
                    "Registration Required",
                    "You are not registered. Use /register <mc_username> first.",
                    "warning",
                )
                return
            if amount <= 0:
                await self._send_embed(ctx, "Invalid Amount", "Withdrawal amount must be greater than zero.", "warning")
                return
            current_balance = db_finance.get_balance(discord_id)
            if current_balance < amount:
                await self._send_embed(ctx, "Insufficient Funds", "You do not have enough balance for this withdrawal.", "warning")
                return
            await self._send_embed(ctx, "Request Submitted", "Your withdrawal request has been submitted.", "success")
            db_requests.add_request(discord_id, "withdrawal", "pending")

            if withdrawal_requests_channel:
                logs = self._build_embed("Withdrawal Request", "A new withdrawal request is pending review.", "warning")
                logs.add_field(name="User", value=f"{ctx.author} (ID: {discord_id})")
                logs.add_field(name="Amount", value=f"{amount}Z$")
                await withdrawal_requests_channel.send(embed=logs)
        except Exception:
            await self._send_error(ctx)

    @commands.hybrid_command()
    async def request_deposit(self, ctx: commands.Context, amount: float):
        try:
            deposit_requests_channel = self.bot.get_channel(self.deposit_requests_channel_id)
            db_finance = FinanceDB()
            db_requests = RequestsDB()
            discord_id = ctx.author.id
            if not db_finance.user_exists(discord_id):
                await self._send_embed(
                    ctx,
                    "Registration Required",
                    "You are not registered. Use /register <mc_username> first.",
                    "warning",
                )
                return
            if amount <= 0:
                await self._send_embed(ctx, "Invalid Amount", "Deposit amount must be greater than zero.", "warning")
                return
            await self._send_embed(ctx, "Request Submitted", "Your deposit request has been submitted.", "success")
            db_requests.add_request(discord_id, "deposit", "pending")

            if deposit_requests_channel:
                logs = self._build_embed("Deposit Request", "A new deposit request is pending review.", "info")
                logs.add_field(name="User", value=f"{ctx.author} (ID: {discord_id})")
                logs.add_field(name="Amount", value=f"{amount}Z$")
                await deposit_requests_channel.send(embed=logs)
        except Exception:
            await self._send_error(ctx)

    @commands.hybrid_command()
    async def request_loan(self, ctx: commands.Context, amount: float):
        try:
            loan_requests_channel = self.bot.get_channel(self.loan_requests_channel_id)
            db_finance = FinanceDB()
            db_requests = RequestsDB()
            discord_id = ctx.author.id
            if not db_finance.user_exists(discord_id):
                await self._send_embed(
                    ctx,
                    "Registration Required",
                    "You are not registered. Use /register <mc_username> first.",
                    "warning",
                )
                return
            if amount <= 0:
                await self._send_embed(ctx, "Invalid Amount", "Loan amount must be greater than zero.", "warning")
                return
            await self._send_embed(ctx, "Request Submitted", "Your loan request has been submitted.", "success")
            db_requests.add_request(discord_id, "loan", "pending")

            if loan_requests_channel:
                logs = self._build_embed("Loan Request", "A new loan request is pending review.", "primary")
                logs.add_field(name="User", value=f"{ctx.author} (ID: {discord_id})")
                logs.add_field(name="Amount", value=f"{amount}Z$")
                await loan_requests_channel.send(embed=logs)
        except Exception:
            await self._send_error(ctx)

    @commands.hybrid_command()
    @app_commands.default_permissions(administrator=True)
    async def approve_request(self, ctx: commands.Context, request_id: int):
        try:
            db_requests = RequestsDB()
            request = db_requests.get_request(request_id)
            if request:
                _, _, _, status, _ = request
                if status != "pending":
                    await self._send_embed(ctx, "Request Already Processed", "This request has already been processed.", "warning")
                    return
                db_requests.update_request_status(request_id, "approved")
                await self._send_embed(ctx, "Request Approved", f"Request ID {request_id} has been approved.", "success")
            else:
                await self._send_embed(ctx, "Request Not Found", "No request exists with that ID.", "warning")
        except Exception:
            await self._send_error(ctx)

    @commands.hybrid_command()
    @app_commands.default_permissions(administrator=True)
    async def deny_request(self, ctx: commands.Context, request_id: int):
        try:
            db_requests = RequestsDB()
            request = db_requests.get_request(request_id)
            if request:
                _, _, _, status, _ = request
                if status != "pending":
                    await self._send_embed(ctx, "Request Already Processed", "This request has already been processed.", "warning")
                    return
                db_requests.update_request_status(request_id, "denied")
                await self._send_embed(ctx, "Request Denied", f"Request ID {request_id} has been denied.", "error")
            else:
                await self._send_embed(ctx, "Request Not Found", "No request exists with that ID.", "warning")
        except Exception:
            await self._send_error(ctx)

    @app_commands.command(name="request_approve", description="Approve a pending request by ID.")
    @app_commands.default_permissions(administrator=True)
    async def request_approve(self, interaction: discord.Interaction, request_id: int):
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if not member or not member.guild_permissions.administrator:
            await self._send_interaction_text(interaction, "Permission Denied", "You must be an administrator to use this command.", "error")
            return

        await self.ui_admin_approve_request(interaction, request_id)

    @app_commands.command(name="request_deny", description="Deny a pending request by ID.")
    @app_commands.default_permissions(administrator=True)
    async def request_deny(self, interaction: discord.Interaction, request_id: int):
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if not member or not member.guild_permissions.administrator:
            await self._send_interaction_text(interaction, "Permission Denied", "You must be an administrator to use this command.", "error")
            return

        await self.ui_admin_deny_request(interaction, request_id)

    @commands.hybrid_command()
    @app_commands.default_permissions(administrator=True)
    async def get_all_requests(self, ctx: commands.Context):
        try:
            db_requests = RequestsDB()
            requests = db_requests.get_all_requests()
            if requests:
                request_lines = [self._format_request_line(request_row) for request_row in requests]
                await self._send_lines_as_embeds(ctx, "All Requests", request_lines, "info")
            else:
                await self._send_embed(ctx, "All Requests", "No requests found.", "warning")
        except Exception:
            await self._send_error(ctx)

    @commands.hybrid_command()
    @app_commands.default_permissions(administrator=True)
    async def get_request_by_id(self, ctx: commands.Context, request_id: int):
        try:
            db_requests = RequestsDB()
            request = db_requests.get_request(request_id)
            if request:
                row_request_id, discord_id, request_type, status, created_at = request
                embed = self._build_embed("Request Details", "Detailed request information:", "info")
                embed.add_field(name="Request ID", value=str(row_request_id), inline=True)
                embed.add_field(name="Discord User", value=self._discord_user_label(discord_id), inline=False)
                embed.add_field(name="Type", value=request_type, inline=True)
                embed.add_field(name="Status", value=status, inline=True)
                embed.add_field(name="Created", value=format_discord_timestamp(created_at), inline=False)
                await ctx.send(embed=embed)
            else:
                await self._send_embed(ctx, "Request Not Found", "No request exists with that ID.", "warning")
        except Exception:
            await self._send_error(ctx)

    @commands.hybrid_command()
    @app_commands.default_permissions(administrator=True)
    async def get_requests_by_status(self, ctx: commands.Context, status: str):
        try:
            db_requests = RequestsDB()
            requests = db_requests.get_requests_by_status(status)
            if requests:
                request_lines = [
                    f"• ID {request_id} | {self._discord_user_label(discord_id)} | {request_type} | {status} | {format_discord_timestamp(created_at)}"
                    for request_id, discord_id, request_type, status, created_at in requests
                ]
                await self._send_lines_as_embeds(ctx, f"Requests with Status '{status}'", request_lines, "info")
            else:
                await self._send_embed(ctx, "No Matching Requests", f"No requests found with status '{status}'.", "warning")
        except Exception:
            await self._send_error(ctx)

    @commands.hybrid_command()
    @app_commands.default_permissions(administrator=True)
    async def get_requests_by_discord_id(self, ctx: commands.Context, discord_id: int):
        try:
            db_requests = RequestsDB()
            requests = db_requests.get_requests_by_discord_id(discord_id)
            if requests:
                request_lines = [
                    f"• ID {request_id} | {self._discord_user_label(discord_id)} | {request_type} | {status} | {format_discord_timestamp(created_at)}"
                    for request_id, discord_id, request_type, status, created_at in requests
                ]
                await self._send_lines_as_embeds(ctx, f"Requests for Discord ID '{discord_id}'", request_lines, "info")
            else:
                await self._send_embed(ctx, "No Matching Requests", f"No requests found for Discord ID '{discord_id}'.", "warning")
        except Exception:
            await self._send_error(ctx)

    @commands.hybrid_command()
    @app_commands.default_permissions(administrator=True)
    async def set_balance(self, ctx: commands.Context, mc_username: str, new_balance: float):
        try:
            db = FinanceDB()
            user = db.get_user_by_mc_username(mc_username)
            if user:
                discord_id, mc_username, _ = user
                db.cursor.execute("UPDATE users SET balance = %s WHERE discord_id = %s", (new_balance, discord_id))
                db.conn.commit()
                await self._send_embed(
                    ctx,
                    "Balance Updated",
                    f"Balance for {mc_username} has been updated to {new_balance}Z$.",
                    "success",
                )
            else:
                await self._send_embed(ctx, "User Not Found", "No user exists with that Minecraft username.", "warning")
        except Exception:
            await self._send_error(ctx)

    @commands.hybrid_command()
    @app_commands.default_permissions(administrator=True)
    async def add_balance(self, ctx: commands.Context, mc_username: str, amount: float):
        try:
            if amount <= 0:
                await self._send_embed(ctx, "Invalid Amount", "Amount must be greater than zero.", "warning")
                return

            db = FinanceDB()
            user = db.get_user_by_mc_username(mc_username)
            if user:
                discord_id, mc_username, balance = user
                new_balance = self._to_float(balance) + amount
                db.cursor.execute("UPDATE users SET balance = %s WHERE discord_id = %s", (new_balance, discord_id))
                db.conn.commit()
                await self._send_embed(
                    ctx,
                    "Balance Added",
                    f"Added {amount}Z$ to {mc_username}'s balance. New balance is {new_balance}Z$.",
                    "success",
                )
            else:
                await self._send_embed(ctx, "User Not Found", "No user exists with that Minecraft username.", "warning")
        except Exception:
            await self._send_error(ctx)

    @commands.hybrid_command()
    @app_commands.default_permissions(administrator=True)
    async def remove_balance(self, ctx: commands.Context, mc_username: str, amount: float):
        try:
            if amount <= 0:
                await self._send_embed(ctx, "Invalid Amount", "Amount must be greater than zero.", "warning")
                return

            db = FinanceDB()
            user = db.get_user_by_mc_username(mc_username)
            if user:
                discord_id, mc_username, balance = user
                new_balance = self._to_float(balance) - amount
                if new_balance < 0:
                    await self._send_embed(
                        ctx,
                        "Insufficient Funds",
                        f"Cannot remove {amount}Z$ from {mc_username}'s balance.",
                        "warning",
                    )
                    return
                db.cursor.execute("UPDATE users SET balance = %s WHERE discord_id = %s", (new_balance, discord_id))
                db.conn.commit()
                await self._send_embed(
                    ctx,
                    "Balance Removed",
                    f"Removed {amount}Z$ from {mc_username}'s balance. New balance is {new_balance}Z$.",
                    "success",
                )
            else:
                await self._send_embed(ctx, "User Not Found", "No user exists with that Minecraft username.", "warning")
        except Exception:
            await self._send_error(ctx)

    @commands.hybrid_command()
    async def transfer(self, ctx: commands.Context, mc_username: str, amount: float):
        try:
            transactions_logs = self.bot.get_channel(self.transactions_logs_channel_id)
            db = FinanceDB()
            db1 = TransactionsDB()
            sender_discord_id = ctx.author.id
            if not db.user_exists(sender_discord_id):
                await self._send_embed(
                    ctx,
                    "Registration Required",
                    "You are not registered. Use /register <mc_username> first.",
                    "warning",
                )
                return

            sender_balance = self._to_float(db.get_balance(sender_discord_id))
            if sender_balance < amount:
                await self._send_embed(ctx, "Insufficient Funds", "You do not have enough balance for this transfer.", "warning")
                return

            recipient = db.get_user_by_mc_username(mc_username)
            if not recipient:
                await self._send_embed(ctx, "Recipient Not Found", "Recipient user was not found.", "warning")
                return

            recipient_discord_id, _, recipient_balance = recipient
            recipient_balance = self._to_float(recipient_balance)

            new_sender_balance = sender_balance - amount
            new_recipient_balance = recipient_balance + amount

            db.cursor.execute("UPDATE users SET balance = %s WHERE discord_id = %s", (new_sender_balance, sender_discord_id))
            db.cursor.execute("UPDATE users SET balance = %s WHERE discord_id = %s", (new_recipient_balance, recipient_discord_id))
            db.conn.commit()
            db1.add_transaction(sender_discord_id, amount, "transfer")
            embed = self._build_embed("Transfer Complete", "Funds moved successfully.", "success")
            embed.add_field(name="Recipient", value=mc_username, inline=True)
            embed.add_field(name="Amount", value=f"{amount}Z$", inline=True)
            embed.add_field(name="New Balance", value=f"{new_sender_balance}Z$", inline=False)
            await ctx.send(embed=embed)

            if transactions_logs:
                logs = self._build_embed("Transaction Event", "Transfer recorded in the ledger.", "muted")
                logs.add_field(name="Sender ID", value=f"{sender_discord_id}")
                logs.add_field(name="Receiver ID", value=f"{recipient_discord_id}")
                logs.add_field(name="Amount", value=f"{amount}Z$")
                await transactions_logs.send(embed=logs)
        except Exception:
            await self._send_error(ctx)

    @commands.hybrid_command()
    @app_commands.default_permissions(administrator=True)
    async def loan(self, ctx: commands.Context, mc_username: str, amount: float, due_date: str):
        try:
            db = FinanceDB()
            db1 = BankDB()
            user = db.get_user_by_mc_username(mc_username)
            interest_rate = 0.0
            if user:
                if amount <= 0:
                    await self._send_embed(ctx, "Invalid Amount", "Loan amount must be greater than zero.", "warning")
                    return
                discord_id, _, balance = user
                if db1.get_loan(discord_id):
                    await self._send_embed(ctx, "Loan Exists", f"{mc_username} already has an active loan.", "warning")
                    return
                if amount == 1 or amount <= 9:
                    interest_rate = self.zitcoins_1_9_interest_rate
                elif 10 <= amount <= 32:
                    interest_rate = self.zitcoins_10_32_interest_rate
                elif 33 <= amount <= 64:
                    interest_rate = self.zitcoins_32_64_interest_rate
                else:
                    interest_rate = self.zitcoins_above_64_interest_rate
                db1.add_loan(discord_id, amount, interest_rate, due_date)

                new_balance = self._to_float(balance) + amount
                db.cursor.execute("UPDATE users SET balance = %s WHERE discord_id = %s", (new_balance, discord_id))
                db.conn.commit()

                total_repayment = amount * (1 + interest_rate)
                embed = self._build_embed("Loan Created", "A loan has been issued.", "success")
                embed.add_field(name="User", value=mc_username, inline=True)
                embed.add_field(name="Amount", value=f"{amount}Z$", inline=True)
                embed.add_field(name="Interest", value=f"{interest_rate * 100}%", inline=True)
                embed.add_field(name="Total Repayment", value=f"{total_repayment}Z$", inline=True)
                embed.add_field(name="New Balance", value=f"{new_balance}Z$", inline=True)
                embed.add_field(name="Due Date", value=due_date, inline=False)
                await ctx.send(embed=embed)
            else:
                await self._send_embed(ctx, "User Not Found", "No user exists with that Minecraft username.", "warning")
        except Exception:
            await self._send_error(ctx)

    @commands.hybrid_command()
    @app_commands.default_permissions(administrator=True)
    async def get_loan(self, ctx: commands.Context, mc_username: str):
        try:
            db = FinanceDB()
            db1 = BankDB()
            user = db.get_user_by_mc_username(mc_username)
            if user:
                discord_id, mc_username, _ = user
                loan = db1.get_loan(discord_id)
                if loan:
                    _, amount, interest_rate, due_date = loan
                    amount = self._to_float(amount)
                    interest_rate = self._to_float(interest_rate)
                    total_repayment = amount * (1 + interest_rate)
                    embed = self._build_embed("Loan Details", f"Loan details for {mc_username}:", "info")
                    embed.add_field(name="Amount", value=f"{amount}Z$", inline=True)
                    embed.add_field(name="Interest Rate", value=f"{interest_rate * 100}%", inline=True)
                    embed.add_field(name="Total Repayment", value=f"{total_repayment}Z$", inline=True)
                    embed.add_field(name="Due Date", value=f"{due_date}", inline=False)
                    await ctx.send(embed=embed)
                else:
                    await self._send_embed(ctx, "Loan Not Found", f"No loan found for {mc_username}.", "warning")
            else:
                await self._send_embed(ctx, "User Not Found", "No user exists with that Minecraft username.", "warning")
        except Exception:
            await self._send_error(ctx)

    @commands.hybrid_command()
    @app_commands.default_permissions(administrator=True)
    async def get_all_loans(self, ctx: commands.Context):
        try:
            db1 = BankDB()
            loans = db1.get_all_loans()
            if loans:
                loan_lines = [
                    f"• {self._discord_user_label(discord_id)} | principal {self._to_float(amount)}Z$ | rate {self._to_float(interest_rate) * 100}% | total {(self._to_float(amount) * (1 + self._to_float(interest_rate)))}Z$ | due {due_date}"
                    for discord_id, amount, interest_rate, due_date in loans
                ]
                await self._send_lines_as_embeds(ctx, "All Loans", loan_lines, "info")
            else:
                await self._send_embed(ctx, "All Loans", "No loans found.", "warning")
        except Exception:
            await self._send_error(ctx)

    @commands.hybrid_command()
    @app_commands.default_permissions(administrator=True)
    async def remove_loan(self, ctx: commands.Context, mc_username: str):
        try:
            db = FinanceDB()
            db1 = BankDB()
            user = db.get_user_by_mc_username(mc_username)
            if user:
                discord_id, mc_username, _ = user
                loan = db1.get_loan(discord_id)
                if loan:
                    db1.remove_loan(discord_id)
                    await self._send_embed(ctx, "Loan Removed", f"Loan for {mc_username} has been removed.", "success")
                else:
                    await self._send_embed(ctx, "Loan Not Found", f"No loan found for {mc_username}.", "warning")
            else:
                await self._send_embed(ctx, "User Not Found", "No user exists with that Minecraft username.", "warning")
        except Exception:
            await self._send_error(ctx)

    @commands.hybrid_command()
    @app_commands.default_permissions(administrator=True)
    async def get_user(self, ctx: commands.Context, mc_username: str):
        try:
            db = FinanceDB()
            user = db.get_user_by_mc_username(mc_username)
            if user:
                discord_id, mc_username, balance = user
                embed = self._build_embed("User Found", "Account details:", "info")
                embed.add_field(name="Discord User", value=self._discord_user_label(discord_id), inline=False)
                embed.add_field(name="Minecraft Username", value=mc_username, inline=True)
                embed.add_field(name="Balance", value=f"{balance}Z$", inline=True)
                await ctx.send(embed=embed)
            else:
                await self._send_embed(ctx, "User Not Found", "No user exists with that Minecraft username.", "warning")
        except Exception:
            await self._send_error(ctx)

    @commands.hybrid_command()
    @app_commands.default_permissions(administrator=True)
    async def get_user_by_discord_id(self, ctx: commands.Context, discord_id: int):
        try:
            db = FinanceDB()
            user = db.get_user_by_discord_id(discord_id)
            if user:
                discord_id, mc_username, balance = user
                embed = self._build_embed("User Found", "Account details:", "info")
                embed.add_field(name="Discord User", value=self._discord_user_label(discord_id), inline=False)
                embed.add_field(name="Minecraft Username", value=mc_username, inline=True)
                embed.add_field(name="Balance", value=f"{balance}Z$", inline=True)
                await ctx.send(embed=embed)
            else:
                await self._send_embed(ctx, "User Not Found", "No user exists with that Discord ID.", "warning")
        except Exception:
            await self._send_error(ctx)

    @commands.hybrid_command()
    @app_commands.default_permissions(administrator=True)
    async def get_all_users(self, ctx: commands.Context):
        try:
            db = FinanceDB()
            users = db.get_all_users()
            if users:
                user_lines = [
                    f"• {self._discord_user_label(discord_id)} | {mc_username} | {balance}Z$"
                    for discord_id, mc_username, balance in users
                ]
                await self._send_lines_as_embeds(ctx, "All Users", user_lines, "info")
            else:
                await self._send_embed(ctx, "All Users", "No users found.", "warning")
        except Exception:
            await self._send_error(ctx)


class ZitcoinUserView(discord.ui.View):
    def __init__(self, cog: BankingCog, owner_id: int):
        super().__init__(timeout=180)
        self.cog = cog
        self.owner_id = owner_id
        self.add_item(ZitcoinUserSelect(cog))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await self.cog._send_interaction_text(
                interaction,
                "Panel Locked",
                "This panel belongs to another user. Run /zitcoin to open your own panel.",
                "warning",
            )
            return False
        return True


class ZitcoinUserSelect(discord.ui.Select):
    def __init__(self, cog: BankingCog):
        self.cog = cog
        options = [
            discord.SelectOption(label="Check Balance", value="balance", description="View your current balance"),
            discord.SelectOption(label="Transfer ZitCoin", value="transfer", description="Send ZitCoin to another user"),
            discord.SelectOption(label="Request Withdrawal", value="request_withdrawal", description="Submit a withdrawal request"),
            discord.SelectOption(label="Request Deposit", value="request_deposit", description="Submit a deposit request"),
            discord.SelectOption(label="Request Loan", value="request_loan", description="Submit a loan request"),
        ]
        super().__init__(placeholder="Choose a ZitCoin action...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        if selected == "balance":
            await self.cog.ui_user_balance(interaction)
            return
        if selected == "transfer":
            await interaction.response.send_modal(UserTransferModal(self.cog))
            return
        if selected == "request_withdrawal":
            await interaction.response.send_modal(UserRequestAmountModal(self.cog, "withdrawal"))
            return
        if selected == "request_deposit":
            await interaction.response.send_modal(UserRequestAmountModal(self.cog, "deposit"))
            return
        if selected == "request_loan":
            await interaction.response.send_modal(UserRequestAmountModal(self.cog, "loan"))


class ZitcoinAdminView(discord.ui.View):
    def __init__(self, cog: BankingCog, owner_id: int):
        super().__init__(timeout=180)
        self.cog = cog
        self.owner_id = owner_id
        self.add_item(ZitcoinAdminSelect(cog))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await self.cog._send_interaction_text(
                interaction,
                "Panel Locked",
                "This admin panel belongs to another user. Run /zitcoin_admin to open your own panel.",
                "warning",
            )
            return False

        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if not member or not member.guild_permissions.administrator:
            await self.cog._send_interaction_text(interaction, "Permission Denied", "You must be an administrator to use this panel.", "error")
            return False
        return True


class ZitcoinAdminSelect(discord.ui.Select):
    def __init__(self, cog: BankingCog):
        self.cog = cog
        options = [
            discord.SelectOption(label="Approve Request", value="approve_request", description="Approve a pending request"),
            discord.SelectOption(label="Deny Request", value="deny_request", description="Deny a pending request"),
            discord.SelectOption(label="Set Balance", value="set_balance", description="Set a user's balance"),
            discord.SelectOption(label="Add Balance", value="add_balance", description="Add funds to a user"),
            discord.SelectOption(label="Remove Balance", value="remove_balance", description="Remove funds from a user"),
            discord.SelectOption(label="Create Loan", value="create_loan", description="Create a loan for a user"),
            discord.SelectOption(label="Remove Loan", value="remove_loan", description="Remove a user's loan"),
            discord.SelectOption(label="Get All Requests", value="get_all_requests", description="Show all requests"),
            discord.SelectOption(label="Get All Users", value="get_all_users", description="Show all users"),
            discord.SelectOption(label="Get All Loans", value="get_all_loans", description="Show all loans"),
        ]
        super().__init__(placeholder="Choose an admin action...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        if selected == "approve_request":
            await interaction.response.send_modal(AdminRequestIdModal(self.cog, "approve"))
            return
        if selected == "deny_request":
            await interaction.response.send_modal(AdminRequestIdModal(self.cog, "deny"))
            return
        if selected == "set_balance":
            await interaction.response.send_modal(AdminBalanceActionModal(self.cog, "set"))
            return
        if selected == "add_balance":
            await interaction.response.send_modal(AdminBalanceActionModal(self.cog, "add"))
            return
        if selected == "remove_balance":
            await interaction.response.send_modal(AdminBalanceActionModal(self.cog, "remove"))
            return
        if selected == "create_loan":
            await interaction.response.send_modal(AdminLoanCreateModal(self.cog))
            return
        if selected == "remove_loan":
            await interaction.response.send_modal(AdminRemoveLoanModal(self.cog))
            return
        if selected == "get_all_requests":
            await self.cog.ui_admin_get_all_requests(interaction)
            return
        if selected == "get_all_users":
            await self.cog.ui_admin_get_all_users(interaction)
            return
        if selected == "get_all_loans":
            await self.cog.ui_admin_get_all_loans(interaction)


class UserTransferModal(discord.ui.Modal, title="Transfer ZitCoin"):
    recipient_username = discord.ui.TextInput(label="Recipient Minecraft Username", max_length=32)
    amount = discord.ui.TextInput(label="Amount (Z$)", placeholder="e.g. 10")

    def __init__(self, cog: BankingCog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = float(self.amount.value)
        except ValueError:
            await self.cog._send_interaction_text(interaction, "Invalid Amount", "Enter a numeric amount.", "warning")
            return

        await self.cog.ui_user_transfer(interaction, self.recipient_username.value.strip(), amount)


class UserRequestAmountModal(discord.ui.Modal):
    amount = discord.ui.TextInput(label="Amount (Z$)", placeholder="e.g. 10")

    def __init__(self, cog: BankingCog, request_type: str):
        super().__init__(title=f"Request {request_type.capitalize()}")
        self.cog = cog
        self.request_type = request_type

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = float(self.amount.value)
        except ValueError:
            await self.cog._send_interaction_text(interaction, "Invalid Amount", "Enter a numeric amount.", "warning")
            return

        await self.cog.ui_user_request(interaction, self.request_type, amount)


class AdminRequestIdModal(discord.ui.Modal):
    request_id = discord.ui.TextInput(label="Request ID", placeholder="e.g. 12")

    def __init__(self, cog: BankingCog, action: str):
        super().__init__(title=f"{action.capitalize()} Request")
        self.cog = cog
        self.action = action

    async def on_submit(self, interaction: discord.Interaction):
        try:
            request_id = int(self.request_id.value)
        except ValueError:
            await self.cog._send_interaction_text(interaction, "Invalid Request ID", "Request ID must be a whole number.", "warning")
            return

        if self.action == "approve":
            await self.cog.ui_admin_approve_request(interaction, request_id)
        else:
            await self.cog.ui_admin_deny_request(interaction, request_id)


class AdminBalanceActionModal(discord.ui.Modal):
    mc_username = discord.ui.TextInput(label="Minecraft Username", max_length=32)
    amount = discord.ui.TextInput(label="Amount (Z$)", placeholder="e.g. 10")

    def __init__(self, cog: BankingCog, action: str):
        super().__init__(title=f"{action.capitalize()} Balance")
        self.cog = cog
        self.action = action

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = float(self.amount.value)
        except ValueError:
            await self.cog._send_interaction_text(interaction, "Invalid Amount", "Enter a numeric amount.", "warning")
            return

        mc_username = self.mc_username.value.strip()
        if self.action == "set":
            await self.cog.ui_admin_set_balance(interaction, mc_username, amount)
        elif self.action == "add":
            await self.cog.ui_admin_add_balance(interaction, mc_username, amount)
        else:
            await self.cog.ui_admin_remove_balance(interaction, mc_username, amount)


class AdminLoanCreateModal(discord.ui.Modal, title="Create Loan"):
    mc_username = discord.ui.TextInput(label="Minecraft Username", max_length=32)
    amount = discord.ui.TextInput(label="Amount (Z$)", placeholder="e.g. 20")
    due_date = discord.ui.TextInput(label="Due Date", placeholder="YYYY-MM-DD")

    def __init__(self, cog: BankingCog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = float(self.amount.value)
        except ValueError:
            await self.cog._send_interaction_text(interaction, "Invalid Amount", "Enter a numeric amount.", "warning")
            return

        await self.cog.ui_admin_create_loan(interaction, self.mc_username.value.strip(), amount, self.due_date.value.strip())


class AdminRemoveLoanModal(discord.ui.Modal, title="Remove Loan"):
    mc_username = discord.ui.TextInput(label="Minecraft Username", max_length=32)

    def __init__(self, cog: BankingCog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.ui_admin_remove_loan(interaction, self.mc_username.value.strip())


async def setup(bot: commands.Bot):
    await bot.add_cog(BankingCog(bot))
