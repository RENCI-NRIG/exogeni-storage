#!/bin/bash
source /usr/share/storage_service/scripts/common-iscsi-manager-functions
CONF_FILE="/etc/storage_service/lvm-iscsi-manager.conf"

function create_vol {
  tid=$1

  show_n_log "Creating Volume..." 2

  lvcreate -L "${SIZE}" -n "${NAME}" "${POOL}" >/dev/null

  # Check exit status code
  if [ $? -ne 0 ]; then
    return 1
  fi

  if [ $? -ne 0 ]; then
    show_n_log "Error creating LV!" 1
    show_n_log "Rolling back! ..." 1
    delete_target "$tid"
    return 1
  fi

  show_n_log "Adding LV to iSCSI target..." 2
  # Create the target, and bind it to the backing volume.
  # Perform as a loop in a subshell, in the event of transient failure.
  (
  for ((i=0; i<${OPERATION_RETRIES=5}; i+=1))
  do
     tgtadm --lld iscsi --op new --mode logicalunit --tid "$tid" --lun "$LUN_ID" -b "${VG_PATH}/${POOL}/${NAME}" && break
     sleep 1
     false
  done
  )

  if [ $? -ne 0 ]; then
    show_n_log "Error adding LV to the iSCSI target!" 1
    show_n_log "Rolling back! ..." 1
    delete_target
    destroy_vol
    return 1
  fi

  return 0
}

function destroy_vol {
  show_n_log "Destroying Logical Volume ${VG_PATH}/${POOL}/${NAME} ..." 2

  lvremove -f "${VG_PATH}/${POOL}/${NAME}" >/dev/null

  # Check exit status code
  if [ $? -ne 0 ]; then
    show_n_log "Error destroying Logical Volume ${VG_PATH}/${POOL}/${NAME}." 1
    return 1
  fi

  show_n_log "Done" 2
  return 0
}

main $@
