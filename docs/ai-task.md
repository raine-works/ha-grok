# AI Task

The *AI Task* entity works with the `ai_task.generate_data` and `ai_task.generate_image` actions. It can also be chosen as the default under Settings → System → General → AI suggestions.

## Generate data

It uses the model selected in the options. With a `structure`, the answer comes back as data in that shape; if xAI's answer isn't valid JSON, the task fails. Image attachments (camera snapshots, media) are sent along. Other file types are rejected.

## Generate image

It uses `grok-imagine-image-2.0`, which xAI bills per image. Generating from attached images is not supported.

## Not available here

The conversation agent doesn't read images. Use this entity for them.
