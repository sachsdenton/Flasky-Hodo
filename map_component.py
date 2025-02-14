
import streamlit.components.v1 as components
import streamlit as st

def handle_site_selection():
    """Handles site selection messages from the map."""
    if 'selected_site' not in st.session_state:
        st.session_state.selected_site = None

    components.html(
        """
        <script>
        window.addEventListener('message', function(e) {
            if (e.data.type === 'site_selected') {
                // Update URL parameters
                const searchParams = new URLSearchParams(window.location.search);
                searchParams.set('site', e.data.siteId);
                window.history.replaceState({}, '', '?' + searchParams.toString());
                
                // Trigger page reload to update the input field
                window.location.reload();
            }
        });
        </script>
        """,
        height=0,
    )

    # Check URL parameters for site selection
    params = st.experimental_get_query_params()
    if "site" in params:
        site_id = params["site"][0]
        st.session_state.selected_site = site_id
        return site_id

    return st.session_state.selected_site
