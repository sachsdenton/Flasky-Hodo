import streamlit.components.v1 as components
import streamlit as st

def handle_site_selection():
    # Initialize component value if not already set
    if 'selected_site' not in st.session_state:
        st.session_state.selected_site = None

    # Create a hidden component to handle the JavaScript event
    components.html(
        """
        <script>
        window.addEventListener('message', function(e) {
            if (e.data.type === 'site_selected') {
                // Send the site ID to Streamlit
                window.Streamlit.setComponentValue(e.data.siteId);
            }
        });
        </script>
        """,
        height=0,
    )

    # Return the selected site ID
    return components.declare_component("site_selector", path=None)()