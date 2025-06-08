#!/usr/bin/env python3
"""
Main entry point for the meteorological wind profile analysis application.
This file handles both Streamlit and Flask deployment modes.
"""

import os
import sys

def main():
    """Main entry point that detects the deployment environment and runs the appropriate app."""
    
    # Check if we're in a Streamlit environment (deployment expects this)
    if len(sys.argv) > 1 and 'streamlit' in ' '.join(sys.argv):
        # We're being run by Streamlit, but we want to run Flask instead
        # Import and run the Flask app directly
        from app import app
        
        # Run Flask app with production settings for deployment
        app.run(
            host='0.0.0.0',
            port=int(os.environ.get('PORT', 5000)),
            debug=False,  # Production mode
            threaded=True
        )
    else:
        # Direct execution - run Flask app
        from app import app
        app.run(
            host='0.0.0.0',
            port=int(os.environ.get('PORT', 5000)),
            debug=True
        )

if __name__ == '__main__':
    main()