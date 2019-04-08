#!/bin/bash
source /usr/share/storage_service/scripts/common-iscsi-manager-functions
CONF_FILE="/etc/storage_service/gluster-iscsi-manager.conf"

function create_vol {
  tid=$1

  show_n_log "Creating Volume..." 2

  # We call "truncate" to allocate the volume, and
  # we remove "B" from the end of size, because "truncate"
  # makes a distinction between "MB" and "M".
  truncate -s "${SIZE%B}" "${GLUSTER_VOL_PATH}/${NAME}" >/dev/null

  # Check exit status code
  if [ $? -ne 0 ]; then
    return 1
  fi

  if [ $? -ne 0 ]; then
    show_n_log "Error creating backing volume on Gluster!" 1
    show_n_log "Rolling back! ..." 1
    delete_target "$tid"
    return 1
  fi

  show_n_log "Adding Gluster volume to iSCSI target..." 2
  # Create the target, and bind it to the backing volume.
  # Perform as a loop in a subshell, in the event of transient failure.
  (
  for ((i=0; i<${OPERATION_RETRIES=5}; i+=1))
  do
     tgtadm --lld iscsi --op new --mode logicalunit --tid "$tid" --lun "$LUN_ID" -b "${GLUSTER_VOL_PATH}/${NAME}" && break
     sleep 1
     false
  done
  )

  if [ $? -ne 0 ]; then
    show_n_log "Error adding Gluster volume to the iSCSI target!" 1
    show_n_log "Rolling back! ..." 1
    delete_target
    destroy_vol
    return 1
  fi

  return 0
}

function destroy_vol {
  show_n_log "Destroying Gluster volume "${GLUSTER_VOL_PATH}/${NAME}" ..." 2

  # Delete the backing file.
  rm -f "${GLUSTER_VOL_PATH}/${NAME}" >/dev/null

  # Check exit status code
  if [ $? -ne 0 ]; then
    show_n_log "Error destroying Gluster volume ${GLUSTER_VOL_PATH}/${NAME}" 1
    return 1
  fi

  show_n_log "Done" 2
  return 0
}

main $@
