.PHONY: pair unpair setup doctor sync stop start logs uninstall
L=me.omi-local.watch
setup: ; ./setup.sh
doctor: ; ./doctor.sh
sync: ; .venv/bin/python -m omi_local.sync
stop: ; launchctl bootout gui/$$(id -u)/$(L)
start: ; launchctl bootstrap gui/$$(id -u) $$HOME/Library/LaunchAgents/$(L).plist
logs: ; tail -n 30 $${OMI_DATA_DIR:-$$HOME/OmiData}/logs/sync-*.log
uninstall: ; -launchctl bootout gui/$$(id -u)/$(L); rm -f $$HOME/Library/LaunchAgents/$(L).plist; @echo "Code/data kept. Remove ~/OmiData manually if you really want to."
pair: ; .venv/bin/python -m omi_local.pairing pair $(ADDR)
unpair: ; .venv/bin/python -m omi_local.pairing unpair
list: ; .venv/bin/python -m omi_local.pairing list
