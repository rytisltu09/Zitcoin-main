import discord
from discord import app_commands
from discord.ext import commands

from financeDatabase import FinanceDB


class OthersCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.palette = {
            "primary": 0x2D5B87,
            "success": 0x2E8B57,
            "warning": 0xD28B26,
            "error": 0xB03A48,
            "info": 0x3F6D63,
        }
        self.zitcoin_to_diamonds_rate = 2
        self.zitcoin_to_iron_rate = 10
        self.zitcoin_to_emerald_rate = 5
        self.zitcoin_to_gold_rate = 3

        self.diamonds_to_zitcoin_rate = 1 / self.zitcoin_to_diamonds_rate
        self.iron_to_zitcoin_rate = 1 / self.zitcoin_to_iron_rate
        self.emerald_to_zitcoin_rate = 1 / self.zitcoin_to_emerald_rate
        self.gold_to_zitcoin_rate = 1 / self.zitcoin_to_gold_rate
        self.zitcoin_member_role_id = 1523049840995733524

    def _embed(self, title: str, description: str, tone: str = "primary") -> discord.Embed:
        return discord.Embed(title=title, description=description, color=self.palette.get(tone, self.palette["primary"]))

    async def _handle_register(self, member: discord.Member, mc_username: str) -> tuple[str, str, str]:
        db = FinanceDB()
        discord_id = member.id
        if db.user_exists(discord_id):
            return "Already Registered", "Your account is already linked.", "warning"

        db.add_user(discord_id, mc_username)
        role = member.guild.get_role(self.zitcoin_member_role_id) if member.guild else None
        if role:
            try:
                await member.add_roles(role)
            except discord.Forbidden:
                pass
        return "Registration Complete", f"Successfully registered with Minecraft username: {mc_username}", "success"

    async def _handle_unregister(self, member: discord.Member) -> tuple[str, str, str]:
        db = FinanceDB()
        discord_id = member.id
        if not db.user_exists(discord_id):
            return "Not Registered", "You are not registered. Use /register <mc_username> first.", "warning"

        db.remove_user(discord_id)
        role = member.guild.get_role(self.zitcoin_member_role_id) if member.guild else None
        if role:
            try:
                await member.remove_roles(role)
            except discord.Forbidden:
                pass
        return "Unregistered", "Your account link has been removed.", "success"

    @commands.hybrid_command()
    @app_commands.default_permissions(administrator=True)
    async def exchange_info(self, ctx: commands.Context):
        embed = self._embed("Exchange Information", "Official exchange rates and currency notes.", "info")
        embed.add_field(
            name="The ZitCoin is a virtual currency used within the Mycelian Republic and beyond for various transactions and activities.",
            value="It can be earned, spent, and exchanged for in-game items or other benefits.",
            inline=False,
        )
        embed.add_field(
            name="ZitCoin is a safe option to protect your treasury from inflation and other economic issues.",
            value="It is designed to maintain its value over time, making it a reliable store of wealth.",
            inline=False,
        )
        embed.add_field(name="Currency", value="ZitCoin (Z$)", inline=False)
        embed.add_field(
            name="ZitCoin to Diamonds Rate",
            value=f"1 ZitCoin = {self.zitcoin_to_diamonds_rate} Diamonds",
            inline=False,
        )
        embed.add_field(
            name="ZitCoin to Iron Rate",
            value=f"1 ZitCoin = {self.zitcoin_to_iron_rate} Iron",
            inline=False,
        )
        embed.add_field(
            name="ZitCoin to Emerald Rate",
            value=f"1 ZitCoin = {self.zitcoin_to_emerald_rate} Emerald",
            inline=False,
        )
        embed.add_field(
            name="ZitCoin to Gold Rate",
            value=f"1 ZitCoin = {self.zitcoin_to_gold_rate} Gold",
            inline=False,
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command()
    @app_commands.default_permissions(administrator=True)
    async def registration_info(self, ctx: commands.Context):
        embed = self._embed("Registration Information", "How to join and leave the ZitCoin system.", "success")
        embed.add_field(
            name="Registering with the ZitCoin Bot",
            value="To register, use the command `/register <mc_username>`. This will link your Discord account with your Minecraft username.",
            inline=False,
        )
        embed.add_field(
            name="Unregistering",
            value="To unregister, use the command `/unregister`. This will remove your registration from the bot.",
            inline=False,
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command()
    async def ping(self, ctx: commands.Context):
        latency_ms = round(self.bot.latency * 1000)
        await ctx.send(embed=self._embed("Pong", f"Latency: {latency_ms} ms", "primary"))

    @commands.hybrid_command()
    async def register(self, ctx: commands.Context, mc_username: str):
        try:
            if not isinstance(ctx.author, discord.Member):
                await ctx.send(embed=self._embed("Guild Only", "This command can only be used in a server.", "warning"))
                return

            title, description, tone = await self._handle_register(ctx.author, mc_username)
            await ctx.send(embed=self._embed(title, description, tone))
        except Exception:
            await ctx.send(embed=self._embed("Unexpected Error", "Something went wrong while processing this command.", "error"))

    @commands.hybrid_command()
    async def unregister(self, ctx: commands.Context):
        try:
            if not isinstance(ctx.author, discord.Member):
                await ctx.send(embed=self._embed("Guild Only", "This command can only be used in a server.", "warning"))
                return

            title, description, tone = await self._handle_unregister(ctx.author)
            await ctx.send(embed=self._embed(title, description, tone))
        except Exception:
            await ctx.send(embed=self._embed("Unexpected Error", "Something went wrong while processing this command.", "error"))

    @app_commands.command(name="zca", description="Post the ZitCoin registration panel with Register/Unregister buttons.")
    @app_commands.default_permissions(administrator=True)
    async def zca(self, interaction: discord.Interaction):
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if not member or not member.guild_permissions.administrator:
            await interaction.response.send_message(
                embed=self._embed("Permission Denied", "You must be an administrator to use this command.", "error"),
                ephemeral=True,
            )
            return

        embed = self._embed(
            "ZitCoin Account Access",
            "ZitCoin powers deposits, withdrawals, loans, and transfers inside the server economy.\n"
            "Use the buttons below to quickly register or unregister your account.",
            "info",
        )
        embed.add_field(name="Register", value="Links your Discord account to your Minecraft username.", inline=False)
        embed.add_field(name="Unregister", value="Removes your linked account from the ZitCoin system.", inline=False)
        embed.add_field(name="Start Banking", value="Opens your personal banking panel (same as /zitcoin).", inline=False)

        await interaction.response.send_message(
            embed=embed,
            view=ZitcoinAccessView(self),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @commands.hybrid_command()
    @app_commands.default_permissions(administrator=True)
    async def remove_user(self, ctx: commands.Context, mc_username: str):
        try:
            db = FinanceDB()
            user = db.get_user_by_mc_username(mc_username)
            if user:
                discord_id, mc_username, _ = user
                db.remove_user(discord_id)
                await ctx.send(embed=self._embed("User Removed", f"User with Minecraft username {mc_username} has been removed.", "success"))
            else:
                await ctx.send(embed=self._embed("User Not Found", "No user exists with that Minecraft username.", "warning"))
        except Exception:
            await ctx.send(embed=self._embed("Unexpected Error", "Something went wrong while processing this command.", "error"))

    @commands.hybrid_command()
    async def convert(self, ctx: commands.Context, amount: float, from_currency: str, to_currency: str):
        try:
            from_currency = from_currency.lower()
            to_currency = to_currency.lower()

            if from_currency == "zitcoin":
                if to_currency == "diamonds":
                    converted_amount = amount * self.zitcoin_to_diamonds_rate
                elif to_currency == "iron":
                    converted_amount = amount * self.zitcoin_to_iron_rate
                elif to_currency == "emerald":
                    converted_amount = amount * self.zitcoin_to_emerald_rate
                elif to_currency == "gold":
                    converted_amount = amount * self.zitcoin_to_gold_rate
                else:
                    await ctx.send(
                        embed=self._embed(
                            "Invalid Currency",
                            "Invalid target currency. Please use diamonds, iron, emerald, or gold.",
                            "warning",
                        )
                    )
                    return
            elif from_currency == "diamonds":
                if to_currency == "zitcoin":
                    converted_amount = amount * self.diamonds_to_zitcoin_rate
                else:
                    await ctx.send(embed=self._embed("Invalid Currency", "Invalid target currency. Please use zitcoin.", "warning"))
                    return
            elif from_currency == "iron":
                if to_currency == "zitcoin":
                    converted_amount = amount * self.iron_to_zitcoin_rate
                else:
                    await ctx.send(embed=self._embed("Invalid Currency", "Invalid target currency. Please use zitcoin.", "warning"))
                    return
            elif from_currency == "emerald":
                if to_currency == "zitcoin":
                    converted_amount = amount * self.emerald_to_zitcoin_rate
                else:
                    await ctx.send(embed=self._embed("Invalid Currency", "Invalid target currency. Please use zitcoin.", "warning"))
                    return
            elif from_currency == "gold":
                if to_currency == "zitcoin":
                    converted_amount = amount * self.gold_to_zitcoin_rate
                else:
                    await ctx.send(embed=self._embed("Invalid Currency", "Invalid target currency. Please use zitcoin.", "warning"))
                    return
            else:
                await ctx.send(
                    embed=self._embed(
                        "Invalid Currency",
                        "Invalid source currency. Please use zitcoin, diamonds, iron, emerald, or gold.",
                        "warning",
                    )
                )
                return

            await ctx.send(
                embed=self._embed(
                    "Conversion Result",
                    f"{amount} {from_currency.capitalize()} is equivalent to {converted_amount} {to_currency.capitalize()}.",
                    "success",
                )
            )
        except Exception:
            await ctx.send(embed=self._embed("Unexpected Error", "Something went wrong while processing this command.", "error"))

    @commands.hybrid_command()
    async def cmds(self, ctx: commands.Context):
        embed = self._embed("ZitCoin Bot Commands", "Available commands at a glance.", "primary")
        embed.add_field(name="/ping", value="Checks the bot's latency.", inline=False)
        embed.add_field(name="/register <mc_username>", value="Registers a user with their Minecraft username.", inline=False)
        embed.add_field(name="/unregister", value="Unregisters a user.", inline=False)
        embed.add_field(
            name="/convert <amount> <from_currency> <to_currency>",
            value="Converts an amount from one currency to another.",
            inline=False,
        )
        embed.add_field(name="/balance", value="Displays the user's balance.", inline=False)
        embed.add_field(name="/request_withdrawal <amount>", value="Requests a withdrawal of the specified amount.", inline=False)
        embed.add_field(name="/request_deposit <amount>", value="Requests a deposit of the specified amount.", inline=False)
        embed.add_field(name="/request_loan <amount>", value="Requests a loan of the specified amount.", inline=False)
        embed.add_field(name="/transfer <mc_username> <amount>", value="Transfers an amount from the sender to the specified user.", inline=False)
        embed.add_field(name="/cmds", value="Displays all available commands.", inline=False)

        avatar_url = self.bot.user.avatar.url if self.bot.user and self.bot.user.avatar else None
        embed.set_author(name="ZitCoin Bot", icon_url=avatar_url)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    cog = OthersCog(bot)
    await bot.add_cog(cog)
    bot.add_view(ZitcoinAccessView(cog))


class ZitcoinAccessView(discord.ui.View):
    def __init__(self, cog: OthersCog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Register", style=discord.ButtonStyle.success, custom_id="zitcoin:register")
    async def register_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                embed=self.cog._embed("Guild Only", "This button can only be used in a server.", "warning"),
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(ZitcoinRegisterModal(self.cog))

    @discord.ui.button(label="Unregister", style=discord.ButtonStyle.danger, custom_id="zitcoin:unregister")
    async def unregister_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                embed=self.cog._embed("Guild Only", "This button can only be used in a server.", "warning"),
                ephemeral=True,
            )
            return

        try:
            title, description, tone = await self.cog._handle_unregister(interaction.user)
            await interaction.response.send_message(embed=self.cog._embed(title, description, tone), ephemeral=True)
        except Exception:
            await interaction.response.send_message(
                embed=self.cog._embed("Unexpected Error", "Something went wrong while processing this action.", "error"),
                ephemeral=True,
            )

    @discord.ui.button(label="Start Banking", style=discord.ButtonStyle.primary, custom_id="zitcoin:start_banking")
    async def start_banking_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                embed=self.cog._embed("Guild Only", "This button can only be used in a server.", "warning"),
                ephemeral=True,
            )
            return

        banking_cog = self.cog.bot.get_cog("BankingCog")
        if not banking_cog:
            await interaction.response.send_message(
                embed=self.cog._embed("Banking Unavailable", "Banking module is not loaded. Try again in a moment.", "error"),
                ephemeral=True,
            )
            return

        # Local import avoids hard dependency ordering at module import time.
        from cogs.banking import ZitcoinUserView

        embed = discord.Embed(
            title="ZitCoin User Panel",
            description="Pick an action from the dropdown below to manage your account.",
            color=banking_cog.palette.get("primary", 0x2D5B87),
        )
        await interaction.response.send_message(
            embed=embed,
            view=ZitcoinUserView(banking_cog, interaction.user.id),
            ephemeral=True,
        )


class ZitcoinRegisterModal(discord.ui.Modal, title="Register for ZitCoin"):
    mc_username = discord.ui.TextInput(label="Minecraft Username", max_length=32, placeholder="e.g. Steve")

    def __init__(self, cog: OthersCog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                embed=self.cog._embed("Guild Only", "This action can only be used in a server.", "warning"),
                ephemeral=True,
            )
            return

        try:
            username = self.mc_username.value.strip()
            if not username:
                await interaction.response.send_message(
                    embed=self.cog._embed("Invalid Username", "Minecraft username cannot be empty.", "warning"),
                    ephemeral=True,
                )
                return

            title, description, tone = await self.cog._handle_register(interaction.user, username)
            await interaction.response.send_message(embed=self.cog._embed(title, description, tone), ephemeral=True)
        except Exception:
            await interaction.response.send_message(
                embed=self.cog._embed("Unexpected Error", "Something went wrong while processing this action.", "error"),
                ephemeral=True,
            )
