# BowlConnector/__init__.py
# Runs once on install - registers rhino_api_sender.py as a Rhino startup command.

import os
import Rhino


def _register_startup():
    try:
        script = os.path.join(os.path.dirname(__file__), "rhino_api_sender.py")
        cmd = '_RunPythonScript "{0}"'.format(script)

        rhino_id = Rhino.RhinoApp.CurrentRhinoId
        settings = Rhino.PlugIns.PlugIn.GetPluginSettings(rhino_id, False)
        settings = settings.GetChild("Options").GetChild("General")

        existing = settings.GetString("StartupCommands", "")
        if cmd not in existing:
            combined = (existing + "\n" + cmd).strip()
            settings.SetString("StartupCommands", combined)
            print("BowlConnector: startup command registered.")
        else:
            print("BowlConnector: already registered.")
    except Exception as e:
        print("BowlConnector: failed to register startup command: " + str(e))


_register_startup()
