from datetime import datetime, timedelta
import pytz
import datetime as dt
import urllib.request
import json
from markdownify import markdownify
import time
import hashlib

import discord
from discord import SelectOption
from discord import app_commands
from discord.ui import Select, View, Button
from discord.ext import tasks

import google_calendar

# from config_example import TOKEN
from config import TOKEN, GROUP_NAME, GROUP_FORM_URL, RESPONSE_COLLECTOR_CHANNEL_ID, MEMBER_ROLES_MESSAGES, \
    TNGAZ_API_KEY, MEMBER_ROLES, THREAD_CHANNEL_IDS, GUILD_ID


async def get_future_event_selectmenu(ctx):
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
intents.guild_scheduled_events = True
intents.members = True
intents.guilds = True
intents.messages = True

client = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(client)

# sync the slash command to your server
@client.event
async def on_ready():
    await tree.sync(guild=discord.Object(id=GUILD_ID))
    poll_events.start()
    # print "ready" in the console when the bot is ready to work
    print("ready")

@client.event
async def on_message(message: discord.Message):
    if message.channel.id in THREAD_CHANNEL_IDS:
        thread_date = int(time.time())
        thread_name = f"{message.author.display_name} - {thread_date}"
        await message.create_thread(name=thread_name)


times = [
    dt.time(hour=0),
    dt.time(hour=6),
    dt.time(hour=12),
    dt.time(hour=18)
]


@tasks.loop(time=times)
async def poll_events():
    events = google_calendar.get_events(10)
    for g in client.guilds:
        if g.id == GUILD_ID:
            guild = g
            break
    guild = guild or client.guilds[0]
    channel = client.get_channel(RESPONSE_COLLECTOR_CHANNEL_ID)
    if not events:
        print('No upcoming events found.')
        return
    discord_events = guild.scheduled_events

    update_string = await update_events(guild, events, discord_events)
    if update_string:
        await channel.send(update_string)


def event_exists(id_hash, discord_events):
    return id_hash in [e.description[-10:] for e in discord_events if len(e.description) >= 10]


def get_event_by_id_hash(id_hash, discord_events):
    event = [e for e in discord_events if len(e.description) >= 10 and e.description.strip()[-10:] == id_hash]
    if event:
        return event[0]
    else:
        return None

async def update_events(guild: discord.Guild, events, discord_events):
    updated = 0
    inserted = 0
    # Prints the start and name of the next 10 events
    for event in events:
        id = event['id']
        id_hash = hashlib.shake_256(str(id).encode()).hexdigest(5)

        start = event['start'].get('dateTime', event['start'].get('date'))
        start_dt = datetime.fromisoformat(start)
        if start_dt.tzinfo is None:
            start_dt = pytz.timezone('MST').localize(start_dt)
        end = event['end'].get('dateTime', event['end'].get('date'))
        end_dt = datetime.fromisoformat(end)
        if end_dt.tzinfo is None:
            end_dt = pytz.timezone('MST').localize(end_dt)
        description = markdownify(event['description'])[:min(989, len(event['description']))].strip() + "\n" + id_hash
        matching_discord_events = [e for e in discord_events if
                                   e.start_time - start_dt == timedelta(0)
                                   and e.name.strip() == event['summary'].strip()]
        event_by_id_hash = get_event_by_id_hash(id_hash, discord_events)
        matching_event = event_by_id_hash
        if not matching_event and matching_discord_events:
            matching_event = matching_discord_events[0]
        if matching_event:
            if matching_event.description.strip() != description:
                await matching_event.edit(
                    description=description
                )
                updated += 1
        else:
            location = event.get('location', "")
            await guild.create_scheduled_event(
                name=event['summary'],
                description=description,
                start_time=start_dt,
                end_time=end_dt,
                location=location)
            inserted += 1
    return f"updated:{updated}, inserted:{inserted}" if updated + inserted > 0 else None


@tree.command(name="generate_events")
async def generate_events(
        ctx,
        pull_count: int
):
    await ctx.response.defer()
    if False and not ctx.interaction.permissions.manage_events:
        return await ctx.send_followup("https://www.youtube.com/watch?v=RfiQYRn7fBg")

    events = google_calendar.get_events(pull_count)
    if not events:
        print('No upcoming events found.')
        return
    discord_events = ctx.guild.scheduled_events

    update_string = await update_events(ctx.guild, events, discord_events)
    await ctx.followup.send(update_string if update_string else "No change")


@tree.command(name="messagecountaudit")
async def message_count_audit(ctx, history_count: int, message_count: int):
    await ctx.response.defer()
    if message_count < 1:
        return await ctx.send_followup("Cannot check for <= 0 messages")
    if history_count < 1:
        history_count = 100
    audited_users = []
    audit_channel = client.get_channel(RESPONSE_COLLECTOR_CHANNEL_ID)
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


@tree.command(name="getcurrentmembers")
async def current_members(ctx):
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


@tree.command(name="getlapsedmembers")
async def lapsed_members(ctx):
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


@tree.command(name="getagedoutmembers")
async def aged_out_members(ctx):
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


@tree.command(name="getattendedmembers")
async def attended_members(ctx,
                           calendar_id: str):
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

@tree.command(name="eventdm")
@app_commands.describe(role ="Who would you like to message?", channel="What channel to send tagged message?")
async def event_dm(
        ctx: discord.Interaction,
        role: discord.Role,
        channel: discord.TextChannel
):
    await ctx.response.defer()
    await client.wait_until_ready()

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
        await client.wait_until_ready()

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
            modal.add_item(discord.InputText(label="Message to send", style=discord.InputTextStyle.long))

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


@client.event
async def on_member_join(member: discord.Member):
    await client.wait_until_ready()

    form_button = Button(
        label="Go to membership form",
        url=GROUP_FORM_URL
    )
    confirm_button = Button(label="Confirm")

    async def confirm_button_callback(button_interaction: discord.Interaction):
        modal = discord.ui.Modal(
            title="Discord New User Form")
        modal.add_item(discord.ui.TextInput(
            label="Scene Name",
            required=True,
            style=discord.TextStyle.short)
        )
        modal.add_item(discord.ui.TextInput(
            label="I am 18 years of age or older: (YES/NO)",
            required=True,
            style=discord.TextStyle.short)
        )
        modal.add_item(discord.ui.TextInput(
            label="How did you find us?",
            required=False,
            style=discord.TextStyle.short)
        )
        modal.add_item(discord.ui.TextInput(
            label="optional: message for approving moderator",
            required=False,
            style=discord.TextStyle.paragraph)
        )

        async def modal_callback(modal_interaction: discord.Interaction):
            await modal_interaction.response.defer()
            nonlocal modal
            nonlocal button_interaction
            modal.stop()

            await client.get_channel(RESPONSE_COLLECTOR_CHANNEL_ID).send(
                f"new Discord membership form for {member.mention}\n"
                + "\n".join(
                    [f"{index}:{child.value}" for index, child in enumerate(modal.children) if len(child.value) > 0]))
            await button_interaction.message.edit(
                content="Your form response has been received. Please wait while a board "
                        "member verifies your response",
                view=None
            )

        modal.on_submit = modal_callback
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


@tree.command(name="join")
async def join_server(ctx):
    await ctx.response.defer()
    await on_member_join(ctx.user)


@tree.command(name="get_ids")
async def get_member_ids(ctx):
    if not ctx.interaction.permissions.moderate_members:
        return await ctx.send_followup("https://www.youtube.com/watch?v=RfiQYRn7fBg")

    with open("members.txt", "w", encoding="utf-8") as file:
        for member in ctx.guild.members:
            file.write(member.name + ', ' + (member.nick or member.name) + ', ' + str(member.id) + "\n")
    with open("members.txt", "rb") as file:
        await ctx.send("Your file is:", file=discord.File(file, "members.txt"))


@client.event
async def on_member_update(before: discord.Member, after: discord.Member):
    if len(before.roles) < len(after.roles):
        new_role = next(role for role in after.roles if role not in before.roles)
        message = MEMBER_ROLES_MESSAGES.get(new_role.id)
        if message:
            await before.send(message)


client.run(TOKEN)