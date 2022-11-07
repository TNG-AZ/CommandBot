import time

import discord
from discord.ext import commands
from discord.ui import Select, View
from discord import SelectOption
from datetime import datetime


#from config_example import TOKEN
from config import TOKEN


async def get_future_event_selectmenu(ctx: discord.ApplicationContext):
    events = await ctx.guild.fetch_scheduled_events()
    events = sorted(
        [e for e in events if e.start_time.date() >= datetime.utcnow().date()],
        key=lambda e: e.start_time.timestamp
    )
    options = []
    for event in events:
        options.append(SelectOption(
            label=f"{event.name} on {event.start_time:%d-%m-%y}",
            value=str(event.id),
            description=event.description
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
    event_options = await get_future_event_selectmenu(ctx)

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
        event_id = event_options.values[0]

        async def message_option_callback(interaction: discord.Interaction):
            nonlocal event_id, event_options

            message_type = message_options.values[0]

            modal = discord.ui.Modal(title="RSVP Mailer")
            modal.add_item(discord.ui.InputText(label="Message to send", style=discord.InputTextStyle.long))

            async def modal_callback(interaction: discord.Interaction):
                nonlocal event_id, message_type, modal
                await ctx.send(f"event:{event_id}, mode:{message_type}, message:{modal.children[0].value}")
                return await interaction.message.delete()

            modal.callback = modal_callback
            return await interaction.response.send_modal(modal)

        message_options.callback = message_option_callback

        view = View(message_options)
        return await interaction.message.edit(view=view)

    event_options.callback = event_select_callback
    view = View(event_options)
    await ctx.respond("", view=view)


bot.run(TOKEN)

