import { Bell } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMarkNotificationRead, useNotifications } from '../hooks/useNotifications';
import { formatDateTime } from '../utils/format';

/** Header bell: unread count and a dropdown of recent notifications for the signed-in user. */
export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const panelRef = useRef(null);
  const { data: notifications = [] } = useNotifications();
  const markRead = useMarkNotificationRead();
  const navigate = useNavigate();
  // A notification with a page (e.g. a finished subtask's day in the weekly log): open it, and it counts as read.
  const openNotification = (notification) => {
    if (!notification.is_read) markRead.mutate(notification.id);
    setOpen(false);
    navigate(notification.link);
  };
  const unread = notifications.filter((notification) => !notification.is_read);

  useEffect(() => {
    if (!open) return undefined;
    function handleClick(event) {
      if (panelRef.current && !panelRef.current.contains(event.target)) setOpen(false);
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [open]);

  return (
    <div className="notification-bell" ref={panelRef}>
      <button
        type="button"
        className="notification-bell-button"
        aria-label={`Notifications (${unread.length} unread)`}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <Bell size={16} />
        {unread.length > 0 && <span className="notification-badge">{unread.length}</span>}
      </button>
      {open && (
        <div className="notification-panel" role="dialog" aria-label="Notifications">
          <strong className="notification-panel-title">Notifications</strong>
          {notifications.length === 0 && <p className="notification-empty">No notifications yet.</p>}
          <ul className="notification-list">
            {notifications.map((notification) => (
              <li
                key={notification.id}
                className={`notification-item${notification.is_read ? '' : ' notification-unread'}`}
              >
                <div className="notification-item-head">
                  <strong>{notification.title}</strong>
                  {!notification.is_read && (
                    <button
                      type="button"
                      className="notification-mark-read"
                      disabled={markRead.isPending}
                      onClick={() => markRead.mutate(notification.id)}
                    >
                      Mark read
                    </button>
                  )}
                </div>
                <p>{notification.message}</p>
                <div className="notification-item-foot">
                  <small>{formatDateTime(notification.created_at)}</small>
                  {notification.link && (
                    <button
                      type="button"
                      className="notification-open"
                      onClick={() => openNotification(notification)}
                    >
                      Open
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
