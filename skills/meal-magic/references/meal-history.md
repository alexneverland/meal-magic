# Actual meals and member history

Read before interpreting actual meal reports, consulting personal meal history, correcting or removing events.

## Actual meal history

Log only a user's unambiguous statement that a meal was actually cooked or eaten.
"Let's make soup" is a plan; "I cooked soup" is `cooked`; "I ate soup" is `eaten`.
Cooking does not imply eating, and eating does not imply cooking. If both were
explicitly reported, record two events. Ask when actual completion or the date
is ambiguous. Resolve relative dates using the user's date/timezone and pass an
explicit ISO calendar date. Do not fabricate a precise time.

Use optional `member_ids` only for explicitly reported members of this actual
event. For `eaten`, these are the people who ate; for `cooked`, they are the
explicitly stated recipients of the prepared food, not the cooks or proof anyone
ate. A prior recipe audience or the default household audience is not evidence
that everyone ate. Resolve clear references in an actual report ("both of them
ate it") from conversation; clarify material ambiguity rather than guessing.
When participants are unspecified, omit `member_ids`; an empty returned list
means unspecified, not "nobody ate". Do not require identifying every diner just
to log an otherwise clear actual event, and never backfill old unknown attendance.

For separate dishes actually eaten by different people, record a separate event
for each dish with its reported diners and its own request key. Use `meal-list`
with `member_id` and `kind=eaten` for that person's recent consumption and variety.
Unspecified events are excluded from personal history; they cannot establish
what that person ate. Cooked events describe preparation, not consumption.

Use a fresh request key for each distinct recipe save or actual meal event, and
reuse the SAME key and payload when retrying an uncertain write. The key is an
opaque identifier, not a meal name or date. If the user repeats a report and it
is unclear whether it describes the already logged event, inspect history and
clarify before writing. A genuine repeat meal or eating leftovers is a separate
event, even on the same day. Never deduplicate by meal-name similarity. A favorite,
recipe save, recipe retrieval, or suggestion never implies cooking or eating.
Remove an incorrect event by ID only when the user requests a correction/removal.
To correct membership, explicitly remove that incorrect event and log its corrected
replacement with a new request key; reuse the key of the replacement on retries.
These are two separate transactions: if interrupted after removal, report that
the replacement is not yet recorded and retry that replacement. Do not silently
delete meal history to remove a member: linked-member removal refuses.
Meal-log receipts survive event removal; replaying the old key returns a historical
response and never recreates the removed event. Check `meal-list` for current state.
Disclose that removal clears the active event and links but retains original
request/response text for retry safety; do not describe it as complete erasure.
