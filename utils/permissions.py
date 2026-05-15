from discord.ext import commands


def is_guild_owner(user, guild):
    return bool(guild and user and user.id == guild.owner_id)


def guild_owner_only():
    async def predicate(ctx):
        return is_guild_owner(ctx.author, ctx.guild)

    return commands.check(predicate)
