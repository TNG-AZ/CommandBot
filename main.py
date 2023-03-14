from datetime import datetime

import discord
from discord import SelectOption
from discord.ui import Select, View, Button

# from config_example import TOKEN
from config import TOKEN, GROUP_NAME, GROUP_FORM_URL, RESPONSE_COLLECTOR_CHANNEL_ID, MEMBER_ROLES_MESSAGES


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
bot = discord.Bot(
    intents=intents,
)


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
                            await sub.send(message)
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
            label="FetLife username",
            required=False,
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
