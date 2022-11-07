import discord
from discord.ext import commands
from discord.ui import Select, View
from discord import SelectOption
from datetime import datetime
from config_example import TOKEN


async def get_future_event_selectmenu(ctx: discord.ApplicationContext):
    events = await ctx.guild.fetch_scheduled_events()
    events = sorted(
        [e for e in events if e.start_time.date() >= datetime.utcnow().date()],
        key=lambda e: e.start_time.timestamp
    )
    options = []
    for event in events:
        print(event.name)
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
bot = discord.Bot(intents=intents)


@bot.slash_command(name="eventdm")
async def event_dm(ctx: discord.ApplicationContext):
    options = await get_future_event_selectmenu(ctx)
    view = View(options)
    await ctx.send("Choose an event", view=view)


bot.run(TOKEN)

