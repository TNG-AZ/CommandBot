import discord
from discord.ui import Select, View, Button
from discord import SelectOption
from datetime import datetime

# from config_example import TOKEN
from config import TOKEN, ADMIN_USER_ID, GROUP_NAME, GROUP_FORM_URL


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
                        return await interaction.message.edit(view=sent_button_view)
                    else:
                        message_with_tag = ", ".join([sub.mention for sub in subscribers])
                        message_with_tag += "\n\n"
                        message_with_tag += message
                        await interaction.message.edit(view=sent_button_view)
                        return await channel.send(message_with_tag) if channel else await ctx.send(message_with_tag)

                confirm_button.callback = confirm_callback
                view = View(confirm_button)
                return await ctx.send(view=view)

            modal.callback = modal_callback
            await interaction.response.send_modal(modal)
            return await interaction.message.delete()

        message_options.callback = message_option_callback
        view = View(message_options)
        return await interaction.message.edit(view=view)

    event_options.callback = event_select_callback
    view = View(event_options)
    await ctx.send_followup("", view=view)


@bot.slash_command(name="join")
async def join_server(ctx: discord.ApplicationContext):
    await ctx.response.defer()
    await bot.wait_until_ready()

    form_button = Button(
        label="Go to membership form",
        url=GROUP_FORM_URL
    )
    confirm_button = Button(label="Confirm")

    async def confirm_button_callback(button_interaction: discord.Interaction):
        if button_interaction.user != ctx.author:
            return

        await button_interaction.message.delete()

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
            modal.stop()

            await bot.get_user(ADMIN_USER_ID).send(
                f"new Discord membership form for {ctx.author.mention}\n"
                + "\n".join([f"{index}:{child.value}" for index, child in enumerate(modal.children) if len(child.value) > 0]))

            return await ctx.send(
                f"Received Discord new user form for {modal_interaction.user.mention}"
            )

        modal.callback = modal_callback
        return await button_interaction.response.send_modal(modal)

    confirm_button.callback = confirm_button_callback
    view = View()
    view.add_item(form_button)
    view.add_item(confirm_button)

    await ctx.send_followup(
        content=f"Please click the form button to go to the {GROUP_NAME} membership form,"
                + " and then click \"Confirm\" once you have completed it",
        view=view
    )


bot.run(TOKEN)
