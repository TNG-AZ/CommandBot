import time

import discord
from discord.ext import commands
from discord.ui import Select, View, Button
from discord import SelectOption
from datetime import datetime

# from config_example import TOKEN
from config import TOKEN


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
            description= event.description if len(event.description) <= 100 else f"{event.description[:97]}..."
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
bot = discord.Bot(
    intents=intents,
)


@bot.slash_command(name="eventdm")
async def event_dm(ctx: discord.ApplicationContext):
    await ctx.response.defer()
    await bot.wait_until_ready()
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

        event_id = event_options.values[0]
        event = await ctx.guild.fetch_scheduled_event(event_id)

        if event.subscriber_count == 0:
            await ctx.send(f"No one seems to be interested in {event.name}")
            return await interaction.message.delete()

        if event.subscriber_count == 1:
            subscribers = await event.subscribers().next()
        else:
            subscribers = await event.subscribers().flatten()

        async def message_option_callback(interaction: discord.Interaction):
            nonlocal event_id, event_options

            message_type = message_options.values[0]

            modal = discord.ui.Modal(title="RSVP Mailer")
            modal.add_item(discord.ui.InputText(label="Message to send", style=discord.InputTextStyle.long))

            async def modal_callback(interaction: discord.Interaction):
                nonlocal event_id, message_type, subscribers, modal
                modal.stop()

                message = modal.children[0].value

                if event.subscriber_count == 1:
                    target_names = subscribers.name
                else:
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
                    await interaction.message.delete()
                    if event.subscriber_count == 1:
                        subscribers = [subscribers]

                    if message_type == "DM":
                        for sub in subscribers:
                            await sub.send(message)
                        await ctx.send(view=View(Button(disabled=True, label="SENT")))
                    else:
                        message_with_tag = ", ".join([sub.mention for sub in subscribers])
                        message_with_tag += "\n\n"
                        message_with_tag += message
                        await ctx.send(message_with_tag)
                    return await interaction.response.defer()

                confirm_button.callback = confirm_callback
                view = View(confirm_button)
                await ctx.send(view=view)
                return await interaction.response.defer()

            modal.callback = modal_callback
            await interaction.response.send_modal(modal)
            return await interaction.message.delete()

        message_options.callback = message_option_callback

        view = View(message_options)
        await interaction.message.edit(view=view)
        return await interaction.response.defer()

    event_options.callback = event_select_callback
    view = View(event_options)
    await ctx.send_followup("", view=view)


bot.run(TOKEN)
