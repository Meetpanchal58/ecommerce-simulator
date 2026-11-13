"""Templates for review and support-contact text (filled in with order details)."""

REVIEW_TEXT = {
    ("Size", "Negative"): ["Size runs small, had to return.", "Ordered my usual size but it was too tight.",
                           "Sizing chart is misleading, way too big."],
    ("Size", "Positive"): ["True to size, fits perfectly.", "Perfect fit, the size guide is accurate."],
    ("Quality", "Negative"): ["Material feels cheap and faded after one wash.", "Stitching came loose within a week."],
    ("Quality", "Positive"): ["Excellent quality fabric, worth the price.", "Very well made, feels premium."],
    ("Quality", "Neutral"): ["Quality is okay for the price.", "Decent product, nothing special."],
    ("Delivery", "Negative"): ["Arrived late, after the promised date.", "Delivery took far too long."],
    ("Delivery", "Positive"): ["Delivered before time, well packed.", "Super fast delivery."],
    ("Price", "Positive"): ["Great deal during the sale!", "Value for money at this price."],
    ("Look", "Positive"): ["Looks exactly like the pictures, love the colour.", "Got many compliments wearing this."],
    ("Look", "Negative"): ["Colour is different from the photos.", "Does not look like the picture."],
}

# Customer messages for each true issue type, written so the issue is not simply a keyword.
TRANSCRIPTS = {
    "Delivery Delay": [
        "Hi, my order {order} was supposed to arrive by {promised} and I still don't have it. Tracking has not moved.",
        "It's past the delivery date for the {product}. I needed it for an occasion, can you tell me where it is?",
        "The app keeps saying arriving tomorrow for order {order}. That was three days ago.",
    ],
    "Not Delivered": [
        "Order {order} shows delivered but nobody at home received anything. Please check.",
        "The courier marked my package as failed delivery but no one came to my address in {city}.",
    ],
    "Refund Delay": [
        "My return for the {product} was picked up but the refund of Rs {amount} hasn't reached me yet.",
        "It's been over a week since you collected the return for {order}. Where is my money?",
    ],
    "Damaged or Wrong Item": [
        "I received the {product} with a tear near the seam. I want a replacement.",
        "The package for {order} had a completely different item inside, not what I ordered.",
    ],
    "Size Exchange": [
        "The {product} doesn't fit. Can I exchange it for the next size instead of a refund?",
        "I want to swap the size of the item in order {order}, how does that work?",
    ],
    "Payment Issue": [
        "Money was deducted from my account but the order didn't go through. Please help.",
        "My UPI payment failed twice and now I see two debits.",
    ],
    "Cancellation Query": [
        "I cancelled order {order} yesterday. When will I get the refund?",
        "Why was my order {order} cancelled? I didn't cancel it.",
    ],
    "Product Question": [
        "Is the {product} available in a bigger size soon? It shows out of stock.",
        "What material is the {product} made of? The description is not clear.",
    ],
}
# How an agent might (inconsistently) tag each true issue in the CRM tool.
AGENT_TAGS = {
    "Delivery Delay": ["Delivery", "Late Delivery", "Tracking"],
    "Not Delivered": ["Delivery", "Not Received", "Courier"],
    "Refund Delay": ["Refund", "Payments", "Return"],
    "Damaged or Wrong Item": ["Product Quality", "Return", "Wrong Item"],
    "Size Exchange": ["Exchange", "Size", "Return"],
    "Payment Issue": ["Payments", "Refund"],
    "Cancellation Query": ["Cancellation", "Refund"],
    "Product Question": ["Pre-sale", "Product Info", "Stock Availability"],
}
TEAM_FOR_ISSUE = {
    "Delivery Delay": "Orders", "Not Delivered": "Orders", "Refund Delay": "Payments",
    "Damaged or Wrong Item": "Returns", "Size Exchange": "Returns", "Payment Issue": "Payments",
    "Cancellation Query": "Orders", "Product Question": "Product Support",
}
