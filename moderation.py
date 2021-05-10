import os
import re
import time
import json

from pyrogram import filters
from pyrogram.raw.functions.account import UpdateStatus

from bot import alemiBot

from util.permission import is_superuser
from util.message import edit_or_reply, is_me
from util.command import filterCommand
from util.time import parse_timedelta
from util.getters import get_text, get_username
from util.decorators import report_error, set_offline
from util.help import HelpCategory

import logging
logger = logging.getLogger(__name__)

HELP = HelpCategory("MODERATION")

censoring = {"MASS": [],
			 "FREE": [],
			 "SPEC" : {} }
try: # TODO not use json, because int keys become strings and I need to recast them on load manually
	with open("data/censoring.json") as f:
		buf = json.load(f)
		for k in buf["SPEC"]:
			censoring["SPEC"][int(k)] = buf["SPEC"][k]
		censoring["MASS"] = [ int(e) for e in buf["MASS"] ]
		censoring["FREE"] = [ int(u) for u in buf["FREE"] ]
except FileNotFoundError:
	with open("data/censoring.json", "w") as f:
		json.dump(censoring, f)
except:
	logger.exception("Failed to load ongoing censor data")
	# ignore

@HELP.add(cmd="[<targets>]")
@alemiBot.on_message(is_superuser & filterCommand(["censor"], list(alemiBot.prefixes), flags=["-list", "-i", "-mass"]))
@report_error(logger)
@set_offline
async def censor_cmd(client, message):
	"""delete messages sent by user

	Start censoring someone in current chat.
	Use flag `-mass` to toggle mass censorship in current chat.
	Users made immune (`free` cmd) will not be affected by mass censoring, use flag `-i` to revoke immunity from someone._cmd
	Use flag `-list` to get censored users in current chat. Messages from self will never be censored.
	More than one target can be specified.
	Instead of specifying targets, you can reply to someone.
	To free someone from censorship, use `.free` command.
	"""
	global censoring
	out = ""
	changed = False
	if message.command["-list"]:
		if message.chat.id not in censoring["SPEC"]:
			out += "` → ` Nothing to display\n"
		else:
			usr_list = await client.get_users(censoring["SPEC"][message.chat.id])
			for u in usr_list:
				out += "` → ` {get_username(u)}\n"
	elif message.command["-mass"]:
		logger.info("Mass censoring chat")
		if message.chat.id not in censoring["MASS"]:
			censoring["MASS"].append(message.chat.id)
			out += "` → ` Mass censoring\n"
			changed = True
	elif len(message.command) > 0 or message.reply_to_message:
		logger.info("Censoring users")
		users_to_censor = []
		if message.reply_to_message:
			users_to_censor.append(message.reply_to_message.from_user)
		if len(message.command) > 0:
			for target in message.command.arg:
				if target == "-delme":
					continue
				if target.isnumeric():
					target = int(target)
				usr = await client.get_users(target)
				if usr is None:
					out += f"`[!] → ` {target} not found\n"
				else:
					users_to_censor.append(usr)
		if message.command["-i"]:
			for u in users_to_censor:
				if u.id in censoring["FREE"]:
					censoring["FREE"].remove(u.id)
					out += f"` → ` {get_username(u)} is no longer immune\n"
					changed = True
		else:
			for u in users_to_censor:
				if message.chat.id not in censoring["SPEC"]:
					censoring["SPEC"][message.chat.id] = []
				censoring["SPEC"][message.chat.id].append(u.id)
				out += f"` → ` Censoring {get_username(u)}\n"
				changed = True
	if out != "":
		await edit_or_reply(message, out)
	else:
		await edit_or_reply(message, "` → ` Nothing to display")
	if changed:
		with open("data/censoring.json", "w") as f:
			json.dump(censoring, f)

@HELP.add(cmd="[<targets>]")
@alemiBot.on_message(is_superuser & filterCommand(["free", "f", "stop"], list(alemiBot.prefixes), flags=["-list", "-i", "-mass"]))
@report_error(logger)
@set_offline
async def free_cmd(client, message):
	"""stop censoring someone

	Stop censoring someone in current chat.
	Use flag `-mass` to stop mass censorship current chat.
	You can add `-i` to make target immune to mass censoring.
	More than one target can be specified (separate with spaces).
	Add `-list` flag to list immune users (censor immunity is global but doesn't bypass specific censorship).
	Instead of specifying targets, you can reply to someone.
	"""
	global censoring
	out = ""
	changed = False
	if message.command["-list"]:
		if censoring["FREE"] == []:
			out += "` → ` Nothing to display\n"
		else:
			immune_users = await client.get_users(censoring["FREE"])
			for u in immune_users:
				out += f"` → ` {get_username(u)}\n"
	elif message.command["-mass"]:
		logger.info("Disabling mass censorship")
		censoring["MASS"].remove(message.chat.id)
		out += "` → ` Restored freedom of speech\n"
		changed = True
	elif len(message.command) > 0 or message.reply_to_message:
		logger.info("Freeing censored users")
		users_to_free = []
		if message.reply_to_message:
			users_to_free.append(message.reply_to_message.from_user)
		if len(message.command) > 0:
			for target in message.command.arg:
				if target == "-delme":
					continue
				if target.isnumeric():
					target = int(target)
				usr = await client.get_users(target)
				if usr is None:
					out += f"`[!] → ` {target} not found\n"
				else:
					users_to_free.append(usr)
		if message.command["-i"]:
			for u in users_to_free:
				censoring["FREE"].append(u.id)
				out += f"` → ` {get_username(u)} is now immune\n"
				changed = True
		else:
			for u in users_to_free:
				if u.id in censoring["SPEC"][message.chat.id]:
					censoring["SPEC"][message.chat.id].remove(u.id)
					out += f"` → ` Freeing {get_username(u)}\n"
					changed = True
	if out != "":
		await edit_or_reply(message, out)
	else:
		await edit_or_reply(message, "` → ` Nothing to display")
	if changed:
		with open("data/censoring.json", "w") as f:
			json.dump(censoring, f)

@alemiBot.on_message(group=9)
async def bully(client, message):
	if message.edit_date is not None:
		return # pyrogram gets edit events as message events!
	if message.chat is None or is_me(message):
		return # can't censor messages outside of chats or from self
	if message.from_user is None:
		return # Don't censory anonymous msgs
	if message.chat.id in censoring["MASS"] \
	and message.from_user.id not in censoring["FREE"]:
		await message.delete()
		await client.send(UpdateStatus(offline=True))
	else:
		if message.chat.id not in censoring["SPEC"] \
		or message.from_user.id not in censoring["SPEC"][message.chat.id]:
			return # Don't censor innocents!
		await message.delete()
		await client.send(UpdateStatus(offline=True))

async def get_user(arg, client):
	if arg.isnumeric():
		return await client.get_users(int(arg))
	else:
		return await client.get_users(arg)

@HELP.add(cmd="[<targets>] [<number>]")
@alemiBot.on_message(is_superuser & filterCommand(["purge", "wipe", "clear"], list(alemiBot.prefixes), options={
	"keyword" : ["-k", "-keyword"],
	"offset" : ["-o", "-offset"],
	"ids" : ["-id"],
	"before" : ["-before"],
	"after" : ["-after"],
	"limit" : ["-lim"]
}, flags=["-all", "-full"]))
@report_error(logger)
@set_offline
async def purge_cmd(client, message):
	"""batch delete messages

	Delete messages last <n> messages (excluding this) sent by <targets> (can be a list of `@user`) matching given filters.
	If <n> is not given, will default to 1.
	If no target is given, messages from author of replied msg or self msgs will be deleted.
	You can give flag `-all` to delete from everyone.
	Search is limited to last 100 messages by default, add the `-full` flag to make an unbound (and maybe long, be careful!) search.
	A keyword (regex) can be specified (`-k`) so that only messages matching given pattern will be deleted.eyboardInterrupt
	An offset can be specified with `-o`, to start deleting after a specific number of messages.
	A time frame can be given: you can limit deletion to messages before (`-before`) a certain time (all messages from now up to <time> ago), \
	or after (`-after`) a certain interval (all messages older than <time>).
	Time can be given as a packed string like this : `8y3d4h15m3s` (years, days, hours, minutes, seconds), \
	any individual token can be given in any position and all are optional, it can just be `30s` or `5m`. If \
	you want to include spaces, wrap the 'time' string in `\"`.
	If you need to purge messages from an user without an @username, you can give its user id with the `-id` flag.
	If you need to provide more than 1 id, wrap them in `\"` and separate with a space.
	"""
	target = []
	opts = {}
	number = 1
	delete_all = bool(message.command["-all"])
	keyword = re.compile(message.command["keyword"]) if "keyword" in message.command else None
	offset = int(message.command["offset"] or 0)
	time_limit = time.time() - parse_timedelta(message.command["before"]).total_seconds() if \
				"before" in message.command else None
	hard_limit = message.command["-full"]
	if "after" in message.command:
		opts["offset_date"] = int(time.time() - parse_timedelta(message.command["after"]).total_seconds())
	if len(message.command) > 0:
		for arg in message.command.arg:
			if arg.startswith("@"):
				if arg == "@me":
					target.append(message.from_user.id)
				else:
					target.append((await get_user(arg, client)).id)
			elif arg.isnumeric():
				number = int(arg)
	if message.command["ids"]:
		for single_id in message.command["ids"].split():
			target.append(int(single_id))
	
	if not target:
		if message.reply_to_message:
			target.append(message.reply_to_message.from_user.id)
		else:
			target.append(message.from_user.id)

	logger.info(f"Purging last {number} message from {target}")
	n = 0
	total = 0
	async for msg in client.iter_history(message.chat.id, **opts):
		total += 1
		if hard_limit and total > max(100, number):
			break
		if msg.message_id == message.message_id: # ignore message that triggered this
			continue
		if ((delete_all or msg.from_user.id in target)
		and (not keyword or keyword.search(get_text(msg)))): # wait WTF why no raw here
			if offset > 0: # do an offset like this because
				offset -=1 #  we want to offset messages from target user, not all messages
				continue
			await msg.delete()
			n += 1
		if n >= number:
			break
		if time_limit is not None and msg.date < time_limit:
			break
	await edit_or_reply(message, "` → ` Done")

