import streamlit.components.v1 as components
import streamlit as st

def handle_site_selection():
    components.html(
        """
        <script>
        window.addEventListener('message', function(e) {
            if (e.data.type === 'site_selected') {
                window.parent.Streamlit.setComponentValue(e.data.siteId);
            }
        });
        </script>
        """,
        height=0,
    )
    
    # Return the selected site ID
    return st.session_state.get('selected_site', None)
