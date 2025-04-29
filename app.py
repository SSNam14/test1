import streamlit as st
import anthropic

# --- Configuration via Sidebar ---
st.sidebar.title("Configuration")
# Prioritize user input, but allow fallback from environment variable if needed
default_key = ""
anthropic_api_key = st.sidebar.text_input(
    "Anthropic API Key",
    type="password",
    value=default_key, # Pre-fill if found in env vars
    help="Get your API key from https://console.anthropic.com/"
)

# Model selection (optional, but good practice)
# Add more models as needed, check Anthropic documentation for latest names
available_models = [
    "claude-3-7-sonnet-20250219",
    "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku-20241022",
    "claude-3-opus-20240229",
    "claude-3-haiku-20240307"
]
selected_model = st.sidebar.selectbox("Select Anthropic Model", available_models, index=0)

# Check if API key is provided
if not anthropic_api_key:
    st.info("Please enter your Anthropic API Key in the sidebar to begin.")
    st.stop() # Halt execution if no key

# --- Initialize Anthropic Client ---
try:
    client = anthropic.Anthropic(api_key=anthropic_api_key)
except Exception as e:
    st.error(f"Failed to initialize Anthropic client: {e}")
    st.stop()

# --- App Title ---
st.title("🐘 Anthropic Claude Chatbot")

# --- Session State Initialization ---
# Maintain the same session state structure
if "messages" not in st.session_state:
    st.session_state.messages = [] # For displaying chat history
if "full_messages" not in st.session_state:
     # For storing the full conversation history for the API call
     # Anthropic uses 'user' and 'assistant' roles, matching OpenAI
    st.session_state.full_messages = []

# --- Display Chat History ---
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- Handle User Input ---
if user_input := st.chat_input("Ask Claude anything..."):
    st.session_state.messages.append({"role": "user", "content": user_input})
    # Append simple user message to full API history
    st.session_state.full_messages.append({"role": "user", "content": user_input})

    # Display user message in chat
    with st.chat_message("user"):
        st.markdown(user_input)

    # --- Get Assistant Response ---
    with st.chat_message("assistant"):
        with st.spinner("Claude is thinking..."): # Add a spinner for user feedback

            # Helper function to handle streaming output for st.write_stream
            def stream_anthropic_response(message_history, model_name):
                try:
                    # Use the 'messages' API with stream=True
                    stream = client.messages.create(
                        model=model_name,
                        max_tokens=4096,  # Required parameter for Anthropic
                        messages=message_history, # Pass the full conversation
                        stream=True,
                    )
                    # Iterate through the stream events
                    for event in stream:
                        # Check for text delta events
                        if event.type == "content_block_delta" and event.delta.type == "text_delta":
                            yield event.delta.text # Yield the text chunk

                # Handle potential API errors gracefully
                except anthropic.APIConnectionError as e:
                    st.error(f"Connection Error: Failed to connect to Anthropic API. {e}")
                    yield f"\n*Error: Could not connect to API.*"
                except anthropic.RateLimitError as e:
                    st.error(f"Rate Limit Error: Anthropic API rate limit exceeded. {e}")
                    yield f"\n*Error: Rate limit exceeded. Please try again later.*"
                except anthropic.AuthenticationError as e:
                    st.error(f"Authentication Error: Invalid Anthropic API key provided. {e}")
                    yield f"\n*Error: Invalid API Key.*"
                except anthropic.APIStatusError as e:
                    st.error(f"API Error: Anthropic API returned an error. Status: {e.status_code}, Response: {e.response}")
                    yield f"\n*Error: API returned status {e.status_code}.*"
                except Exception as e:
                    st.error(f"An unexpected error occurred: {e}")
                    yield f"\n*Error: An unexpected issue occurred.*"


            # Prepare the message history for the API call
            # Make sure roles are 'user' and 'assistant'
            api_messages = [
                {"role": m["role"], "content": m["content"]}
                for m in st.session_state.full_messages
            ]

            # Use st.write_stream with the generator function
            response = st.write_stream(stream_anthropic_response(api_messages, selected_model))

    # Append the complete assistant response to session state
    st.session_state.messages.append({"role": "assistant", "content": response})
    st.session_state.full_messages.append({"role": "assistant", "content": response})

    # Optional: Rerun to ensure the UI updates smoothly after streaming finishes
    st.rerun()
