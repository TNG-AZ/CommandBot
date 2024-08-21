from datetime import datetime, timedelta
import datetime as dt
import urllib.request
import json
from markdownify import markdownify
import time

import discord
from discord import SelectOption
from discord.ui import Select, View, Button
from discord.ext import tasks

import google_calendar

# from config_example import TOKEN
from config import TOKEN, GROUP_NAME, GROUP_FORM_URL, RESPONSE_COLLECTOR_CHANNEL_ID, MEMBER_ROLES_MESSAGES, \
    TNGAZ_API_KEY, MEMBER_ROLES, THREAD_CHANNEL_IDS, GUILD_ID


async def get_future_event_selectmenu(ctx: discord.ApplicationContext):
    events = await ctx.guild.fetch_scheduled_events()
    if not events:
        return

    events = sorted(
        [e for e in events if e.start_time.date() >= datetime.today().date()],
        key=lambda e: e.start_time.timestamp()
    )
    options = []
    for event in events:
        options.append(SelectOption(
            label=f"{event.name} on {event.start_time:%d-%m-%y}",
            value=str(event.id),
            description=event.description if len(event.description) <= 100 else f"{event.description[:97]}..."
        ))
    select = Select(
        placeholder="Select an upcoming event",
        min_values=1,
        max_values=1,
        options=options
    )
    return select


intents = discord.Intents.none()
intents.scheduled_events = True
intents.members = True
intents.guilds = True
intents.messages = True
bot = discord.Bot(
    intents=intents,
)


@bot.event
async def on_message(message: discord.Message):
    if message.channel.id in THREAD_CHANNEL_IDS:
        thread_date = int(time.time())
        thread_name = f"{message.author.display_name} - {thread_date}"
        await message.create_thread(name=thread_name)


@bot.event
async def on_ready():
    poll_events.start()


times = [
    dt.time(hour=0),
    dt.time(hour=6),
    dt.time(hour=12),
    dt.time(hour=18)
]


@tasks.loop(time=times)
async def poll_events():
    events = google_calendar.get_events(10)
    for g in bot.guilds:
        if g.id == GUILD_ID:
            guild = g
            break
    guild = guild or bot.guilds[0]
    channel = bot.get_channel(RESPONSE_COLLECTOR_CHANNEL_ID)
    if not events:
        print('No upcoming events found.')
        return
    discord_events = guild.scheduled_events

    update_string = await update_events(guild, events, discord_events)
    if update_string:
        await channel.send(update_string)


async def update_events(guild: discord.Guild, events, discord_events):
    updated = 0
    inserted = 0
    duplicates_removed = 0
    # Prints the start and name of the next 10 events
    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        # Skip all-day events
        if datetime.fromisoformat(start).tzinfo is None:
            continue

        # This is mostly for debugging because all events *should* have a description, but some of mine don't
        description = None
        if "description" in event:
            description = markdownify(event['description'])[:min(1000, len(event['description']))].strip()
        else:
            description = ""


        matching_discord_events = [e for e in discord_events if
                                   e.start_time - datetime.fromisoformat(start) == timedelta(0)
                                   and e.name.strip() == event['summary'].strip()]
        if len(matching_discord_events) > 0:
            # Remove duplicate events
            if len(matching_discord_events) > 1:
                for i in range(1, len(matching_discord_events)):
                    e = matching_discord_events[i]
                    await e.delete()
                    duplicates_removed += 1
            if matching_discord_events[0].description.strip() != description:
                await matching_discord_events[0].edit(
                    description=description
                )
                updated += 1
        else:
            # The [:100] is also for debugging because it's possible for a location to have more than 100 characters
            location = event.get('location', "")[:100]
            await guild.create_scheduled_event(
                name=event['summary'],
                description=description,
                start_time=datetime.fromisoformat(event['start'].get('dateTime', event['start'].get('date'))),
                end_time=datetime.fromisoformat(event['end'].get('dateTime', event['start'].get('date'))),
                location=location)
            inserted += 1
    return f"updated:{updated}, inserted:{inserted}, duplicates removed: {duplicates_removed}" if updated + inserted + duplicates_removed > 0 else None


@bot.slash_command(name="generate_events")
async def generate_events(
        ctx: discord.ApplicationContext,
        pull_count: int
):
    await ctx.response.defer()
    if not ctx.interaction.permissions.manage_events:
        return await ctx.send_followup("https://www.youtube.com/watch?v=RfiQYRn7fBg")

    events = google_calendar.get_events(pull_count)
    if not events:
        print('No upcoming events found.')
        return
    discord_events = ctx.guild.scheduled_events

    update_string = await update_events(ctx.guild, events, discord_events)
    await ctx.send_followup(update_string if update_string else "No change")


@bot.slash_command(name="messagecountaudit")
async def message_count_audit(ctx: discord.ApplicationContext, history_count: int, message_count: int):
    await ctx.response.defer()
    if message_count < 1:
        return await ctx.send_followup("Cannot check for <= 0 messages")
    if history_count < 1:
        history_count = 100
    audited_users = []
    audit_channel = bot.get_channel(RESPONSE_COLLECTOR_CHANNEL_ID)
    messages = await ctx.channel.history(limit=history_count).flatten()
    for user in ctx.channel.members:
        user_messages = [m for m in messages if m.author.id == user.id]
        if len(user_messages) < message_count:
            audited_users.append(user)
    await audit_channel.send(f"Users who have not sent {message_count} messages out of the last "
                             + f"{history_count} "
                             + f"in the channel {ctx.channel.name}:")
    if len(audited_users) > 0:
        to_send = ""
        for user in audited_users:
            if len(to_send) == 0:
                to_send = user.mention
            else:
                to_send += "\r\n" + user.mention
            if len(to_send) > 1000:
                await audit_channel.send(to_send)
                to_send = ""
        await audit_channel.send(to_send)
    else:
        await audit_channel.send("No users have sent less than N messages")
    await ctx.send_followup("Check audit channel for results")


@bot.slash_command(name="getcurrentmembers")
async def current_members(ctx: discord.ApplicationContext):
    await ctx.response.defer()

    if not ctx.interaction.permissions.manage_roles:
        return await ctx.send_followup("https://www.youtube.com/watch?v=RfiQYRn7fBg")
    to_update = 0
    to_send = ""
    current_member_ids = json.load(
        urllib.request.urlopen("https://tngaz.org/api/discord/current?apiKey=" + TNGAZ_API_KEY))
    for memberId in current_member_ids:
        member = ctx.guild.get_member(memberId)
        if member:
            roles = set([r.id for r in member.roles])
            is_member = len((roles & set(MEMBER_ROLES))) > 0
            if len(to_send) == 0:
                to_send = member.mention + "     " + ("Good" if is_member else "Needs to be updated")
            else:
                to_send += "\r\n" + member.mention + "     " + ("Good" if is_member else "Needs to be updated")
            if is_member:
                to_update += 1
    await ctx.send_followup(to_send + "\r\n\r\n\r\n" + str(to_update) + " left to update")


@bot.slash_command(name="getlapsedmembers")
async def lapsed_members(ctx: discord.ApplicationContext):
    await ctx.response.defer()

    if not ctx.interaction.permissions.manage_roles:
        return await ctx.send_followup("https://www.youtube.com/watch?v=RfiQYRn7fBg")
    to_update = 0
    to_send = ""
    current_member_ids = json.load(
        urllib.request.urlopen("https://tngaz.org/api/discord/lapsed?apiKey=" + TNGAZ_API_KEY))
    for memberId in current_member_ids:
        member = ctx.guild.get_member(memberId)
        if member:
            roles = set([r.id for r in member.roles])
            is_member = len((roles & set(MEMBER_ROLES))) > 0
            if is_member:
                if len(to_send) == 0:
                    to_send = member.mention
                else:
                    to_send += "\r\n" + member.mention
                if is_member:
                    to_update += 1
                if len(to_send) > 1000:
                    await ctx.send_followup(to_send)
                    to_send = ""
    await ctx.send_followup(to_send + "\r\n\r\n\r\n" + str(to_update) + " left to update")


@bot.slash_command(name="getagedoutmembers")
async def aged_out_members(ctx: discord.ApplicationContext):
    await ctx.response.defer()

    if not ctx.interaction.permissions.manage_roles:
        return await ctx.send_followup("https://www.youtube.com/watch?v=RfiQYRn7fBg")
    to_update = 0
    to_send = ""
    current_member_ids = json.load(urllib.request.urlopen("https://tngaz.org/api/discord/aged?apiKey=" + TNGAZ_API_KEY))
    for memberId in current_member_ids:
        member = ctx.guild.get_member(memberId)
        if member:
            roles = set([r.id for r in member.roles])
            is_member = len((roles & set(MEMBER_ROLES))) > 0
            if is_member:
                if len(to_send) == 0:
                    to_send = member.mention
                else:
                    to_send += "\r\n" + member.mention
                if is_member:
                    to_update += 1
                if len(to_send) > 1000:
                    await ctx.send_followup(to_send)
                    to_send = ""
    await ctx.send_followup(to_send + "\r\n\r\n\r\n" + str(to_update) + " left to update")


@bot.slash_command(name="getattendedmembers")
async def attended_members(ctx: discord.ApplicationContext,
                           calendar_id):
    await ctx.response.defer()

    if not ctx.interaction.permissions.manage_roles:
        return await ctx.send_followup("https://www.youtube.com/watch?v=RfiQYRn7fBg")
    to_send = ""
    current_member_ids = json.load(urllib.request.urlopen(
        f"https://tngaz.org/api/discord/attended?apiKey={TNGAZ_API_KEY}&calendarId={calendar_id}")
    )
    for memberId in current_member_ids:
        member = ctx.guild.get_member(memberId)
        if member:
            if len(to_send) == 0:
                to_send = member.mention
            else:
                to_send += "\r\n" + member.mention
            if len(to_send) > 1000:
                await ctx.send_followup(to_send)
                to_send = ""
    await ctx.send_followup(to_send)

@bot.slash_command(name="eventdm")
async def event_dm(
        ctx: discord.ApplicationContext,
        role: discord.Option(discord.Role, "Who would you like to message?", required=False),
        channel: discord.Option(discord.TextChannel, "What channel to send tagged message?", required=False)
):
    await ctx.response.defer()
    await bot.wait_until_ready()

    if not ctx.interaction.permissions.manage_events:
        return await ctx.send_followup("https://www.youtube.com/watch?v=RfiQYRn7fBg")

    event_options = await get_future_event_selectmenu(ctx)

    if not event_options:
        return await ctx.send("no events coming up")

    message_options = Select(
        placeholder="How would you like to deliver the message?",
        min_values=1,
        max_values=1,
        options=[
            SelectOption(label="DM"),
            SelectOption(label="Tagged message")
        ]
    )

    async def event_select_callback(interaction: discord.Interaction):
        await interaction.response.defer()
        await bot.wait_until_ready()

        event_id = event_options.values[0]
        event = await ctx.guild.fetch_scheduled_event(event_id)

        if event.subscriber_count == 0:
            await ctx.send(f"No one seems to be interested in {event.name}")
            return await interaction.message.delete()

        if event.subscriber_count == 1:
            subscribers = [await event.subscribers().next()]
        else:
            subscribers = await event.subscribers().flatten()

        if role:
            subscribers = [sub for sub in subscribers if role in ctx.guild.get_member(sub.id).roles]

        if not subscribers:
            await ctx.send(f"It looks like no one with the role {role.name} is interested in {event.name}")
            return await interaction.message.delete()

        async def message_option_callback(interaction: discord.Interaction):
            nonlocal event_id, event_options

            message_type = message_options.values[0]

            modal = discord.ui.Modal(title="RSVP Mailer")
            modal.add_item(discord.ui.InputText(label="Message to send", style=discord.InputTextStyle.long))

            async def modal_callback(interaction: discord.Interaction):
                nonlocal event_id, message_type, subscribers, modal
                modal.stop()

                message = modal.children[0].value

                target_names = ", ".join([s.name for s in subscribers])

                await interaction.response.send_message(
                    f"""event:{event.name} on {event.start_time:%d-%m-%y}
mode:{message_type}, to:{target_names}
message:{message}"""
                )

                confirm_button = Button(
                    label="Send Message"
                )

                async def confirm_callback(interaction: discord.Interaction):
                    nonlocal subscribers, message

                    await interaction.response.defer()

                    sent_button_view = View(Button(disabled=True, label="SENT"))

                    if message_type == "DM":
                        for sub in subscribers:
                            try:
                                await sub.send(message)
                            except Exception as e:
                                await ctx.send("failed to send message to " + sub.name)
                                await ctx.send(str(e))
                        return await interaction.edit_original_response(view=sent_button_view)
                    else:
                        message_with_tag = ", ".join([sub.mention for sub in subscribers])
                        message_with_tag += "\n\n"
                        message_with_tag += message
                        await interaction.edit_original_response(view=sent_button_view)
                        return await channel.send(message_with_tag) if channel else await ctx.send(message_with_tag)

                confirm_button.callback = confirm_callback
                view = View(confirm_button)
                return await ctx.send(view=view)

            modal.callback = modal_callback
            await interaction.response.send_modal(modal)
            return await interaction.delete_original_response()

        message_options.callback = message_option_callback
        view = View(message_options)
        return await interaction.edit_original_response(view=view)

    event_options.callback = event_select_callback
    view = View(event_options)
    await ctx.send_followup("", view=view)


@bot.event
async def on_member_join(member: discord.Member):
    await bot.wait_until_ready()

    form_button = Button(
        label="Go to membership form",
        url=GROUP_FORM_URL
    )
    confirm_button = Button(label="Confirm")

    async def confirm_button_callback(button_interaction: discord.Interaction):
        modal = discord.ui.Modal(
            title="Discord New User Form")
        modal.add_item(discord.ui.InputText(
            label="Scene Name",
            required=True,
            style=discord.InputTextStyle.short)
        )
        modal.add_item(discord.ui.InputText(
            label="I am 18 years of age or older: (YES/NO)",
            required=True,
            style=discord.InputTextStyle.short)
        )
        modal.add_item(discord.ui.InputText(
            label="How did you find us?",
            required=False,
            style=discord.InputTextStyle.short)
        )
        modal.add_item(discord.ui.InputText(
            label="optional: message for approving moderator",
            required=False,
            style=discord.InputTextStyle.paragraph)
        )

        async def modal_callback(modal_interaction: discord.Interaction):
            await modal_interaction.response.defer()
            nonlocal modal
            nonlocal button_interaction
            modal.stop()

            await bot.get_channel(RESPONSE_COLLECTOR_CHANNEL_ID).send(
                f"new Discord membership form for {member.mention}\n"
                + "\n".join(
                    [f"{index}:{child.value}" for index, child in enumerate(modal.children) if len(child.value) > 0]))
            await button_interaction.message.edit(
                content="Your form response has been received. Please wait while a board "
                        "member verifies your response",
                view=None
            )

        modal.callback = modal_callback
        return await button_interaction.response.send_modal(modal)

    confirm_button.callback = confirm_button_callback
    view = View(timeout=None)
    view.add_item(form_button)
    view.add_item(confirm_button)

    await member.send(
        content=f"Please click the form button to go to the {GROUP_NAME} membership form,"
                " and then click \"Confirm\" once you have completed it",
        view=view
    )


@bot.slash_command(name="join")
async def join_server(ctx: discord.ApplicationContext):
    await on_member_join(ctx.author)
    return await ctx.respond(
        "Check your DMs for instructions on joining the Discord server",
        delete_after=0 if ctx.channel.type == discord.ChannelType.private else 30
    )


@bot.slash_command(name="get_ids")
async def get_member_ids(ctx: discord.ApplicationContext):
    if not ctx.interaction.permissions.moderate_members:
        return await ctx.send_followup("https://www.youtube.com/watch?v=RfiQYRn7fBg")

    with open("members.txt", "w", encoding="utf-8") as file:
        for member in ctx.guild.members:
            file.write(member.name + ', ' + (member.nick or member.name) + ', ' + str(member.id) + "\n")
    with open("members.txt", "rb") as file:
        await ctx.send("Your file is:", file=discord.File(file, "members.txt"))


@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    if len(before.roles) < len(after.roles):
        new_role = next(role for role in after.roles if role not in before.roles)
        message = MEMBER_ROLES_MESSAGES.get(new_role.id)
        if message:
            await before.send(message)


bot.run(TOKEN)
