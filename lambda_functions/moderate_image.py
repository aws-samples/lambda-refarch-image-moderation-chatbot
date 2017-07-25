import os
import urllib
import boto3

SUPPORTED_TYPES = ['image/jpeg', 'image/jpg', 'image/png']  # Supported image types
MAX_SIZE = 5242880  # Max number of image bytes supported by Amazon Rekognition (5MiB)

VERIFICATION_TOKEN = os.environ['VERIFICATION_TOKEN']  # Slack verification token from environment variables
ACCESS_TOKEN = os.environ['ACCESS_TOKEN']  # Slack OAuth access token from environment variables

MIN_CONFIDENCE = float(os.environ['MIN_CONFIDENCE'])  # Confidence interval for image moderation

rekognition = boto3.client('rekognition')


def lambda_handler(event, context):
    print('Validating message...')
    if not verify_token(event):  # Ignore event if verification token presented doesn't match
        return

    if event.get('challenge') is not None:  # Respond to Slack event subscription URL verification challenge
        print('Presented with URL verification challenge- responding accordingly...')
        challenge = event['challenge']
        return {'challenge': challenge}

    if not validate_event(event):  # Ignore event if Slack message doesn't contain any supported images
        return

    event_details = event['event']
    file_details = event_details['file']

    channel = event_details['channel']
    url = file_details['url_private']
    file_id = file_details['id']

    print('Downloading image...')
    image_bytes = download_image(url)
    print('Checking image for explicit content...')
    is_explicit = detect_explicit_content(image_bytes)
    if is_explicit:
        print('Image displays explicit content- deleting from Slack Shared Files...')
        delete_file(file_id)
        print('Posting message to channel to notify users of file deletion...')
        post_message(channel)


def verify_token(event):
    """ Verifies token presented in incoming event message matches the token copied when creating Slack app.

    Args:
        event (dict): Details about incoming event message, including verification token.

    Returns:
        (boolean)
        True if presented with the valid token.
        False otherwise.

    """
    if event['token'] != VERIFICATION_TOKEN:
        print('Presented with invalid token- ignoring message...')
        return False
    return True


def validate_event(event):
    """ Validates event by checking contained Slack message for image of supported type and size.

    Args:
        event (dict): Details about Slack message and any attachements.

    Returns:
        (boolean)
        True if event contains Slack message with supported image size and type.
        False otherwise.
    """
    event_details = event['event']
    file_subtype = event_details.get('subtype')

    if file_subtype != 'file_share':
        print('Not a file_shared event- ignoring event...')
        return False

    file_details = event_details['file']
    mime_type = file_details['mimetype']
    file_size = file_details['size']

    if mime_type not in SUPPORTED_TYPES:
        print('File is not an image- ignoring event...')
        return False

    if file_size > MAX_SIZE:
        print('Image is larger than 5MB and cannot be processed- ignoring event...')
        return False

    return True


def download_image(url):
    """ Download image from private Slack URL using bearer token authorization.

    Args:
        url (string): Private Slack URL for uploaded image.

    Returns:
        (bytes)
        Blob of bytes for downloaded image.


    """
    request = urllib.request.Request(url, headers={'Authorization': 'Bearer %s' % ACCESS_TOKEN})
    return urllib.request.urlopen(request).read()


def detect_explicit_content(image_bytes):
    """ Checks image for explicit or suggestive content using Amazon Rekognition Image Moderation.

    Args:
        image_bytes (bytes): Blob of image bytes.

    Returns:
        (boolean)
        True if Image Moderation detects explicit or suggestive content in blob of image bytes.
        False otherwise.

    """
    try:
        response = rekognition.detect_moderation_labels(
            Image={
                'Bytes': image_bytes,
            },
            MinConfidence=MIN_CONFIDENCE
        )
    except Exception as e:
        print(e)
        print('Unable to detect labels for image.')
        raise(e)
    labels = response['ModerationLabels']
    if not labels:
        return False
    return True


def delete_file(file_id):
    """ Deletes file from Slack team via Slack API.

    Args:
        file_id (string): ID of file to delete.

    Returns:
        (None)
    """
    url = 'https://slack.com/api/files.delete'
    data = urllib.parse.urlencode(
        (
            ("token", ACCESS_TOKEN),
            ("file", file_id)
        )
    )
    data = data.encode("ascii")
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    request = urllib.request.Request(url, data, headers)
    urllib.request.urlopen(request)


def post_message(channel):
    """ Posts message detailing image removal to Slack channel via Slack API.

    Args:
        channel (string): Channel, private group, or IM channel to send message to. Can be an encoded ID, or a name.

    Returns:
        (None)
    """
    url = 'https://slack.com/api/chat.postMessage'
    data = urllib.parse.urlencode(
        (
            ("token", ACCESS_TOKEN),
            ("channel", channel),
            ("text", "File removed due to displaying explicit or suggestive adult content.")
        )
    )
    data = data.encode("ascii")
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    request = urllib.request.Request(url, data, headers)
    urllib.request.urlopen(request)
