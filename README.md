# exogeni-storage
This project aims to provide a dynamic allocation service for various types of storage (iSCSI, NFS, etc.), for use in cloud infrastructure deployments.

As of this time, iSCSI is the only supported allocable resource, but new types will be added in the future. iSCSI support is provided via the Linux iSCSI target daemon.

There are handlers for multiple types of backend storage; currently provided types are:

Linux LVM
ZFS
File-based storage allocated on Gluster
The daemon itself is structured as an XML-RPC web service, using HTTPS as primary transport, and authenticated using standard Apache-style htpasswd files.
