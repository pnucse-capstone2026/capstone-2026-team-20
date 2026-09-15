import { createContext, PropsWithChildren, useContext, useEffect, useMemo, useState } from 'react';

import { EMPTY_GROUP, fetchGroupsWithMembersForUser, GroupWithMembers } from '@/src/services/groups';
import { fetchCurrentUser } from '@/src/services/users';

type GroupSelectionContextValue = {
  groups: GroupWithMembers[];
  selectedGroup: GroupWithMembers;
  selectedGroupId: string;
  setSelectedGroupId: (groupId: string) => void;
  isLoading: boolean;
};

const GroupSelectionContext = createContext<GroupSelectionContextValue | null>(null);

export function GroupSelectionProvider({ children }: PropsWithChildren) {
  const [groups, setGroups] = useState<GroupWithMembers[]>([]);
  const [selectedGroupId, setSelectedGroupId] = useState('');
  const [isLoading, setIsLoading] = useState(true);

  const selectedGroup = useMemo(
    () => groups.find((group) => group.id === selectedGroupId) ?? groups[0] ?? EMPTY_GROUP,
    [groups, selectedGroupId],
  );

  useEffect(() => {
    let isMounted = true;

    fetchCurrentUser()
      .then(async (user) => {
        if (!user) {
          return [];
        }

        return fetchGroupsWithMembersForUser(user.id);
      })
      .then((nextGroups) => {
        if (!isMounted) {
          return;
        }

        setGroups(nextGroups);
        setSelectedGroupId((currentGroupId) => {
          if (nextGroups.length === 0) {
            return '';
          }

          const hasCurrentGroup = nextGroups.some((group) => group.id === currentGroupId);
          return hasCurrentGroup ? currentGroupId : nextGroups[0].id;
        });
      })
      .catch((error) => {
        console.warn('[groups] Failed to load groups', error);
        if (isMounted) {
          setGroups([]);
          setSelectedGroupId('');
        }
      })
      .finally(() => {
        if (isMounted) {
          setIsLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, []);

  const value = useMemo(
    () => ({
      groups,
      selectedGroup,
      selectedGroupId: selectedGroup.id,
      setSelectedGroupId,
      isLoading,
    }),
    [groups, isLoading, selectedGroup],
  );

  return <GroupSelectionContext.Provider value={value}>{children}</GroupSelectionContext.Provider>;
}

export function useGroupSelection() {
  const context = useContext(GroupSelectionContext);

  if (!context) {
    throw new Error('useGroupSelection must be used within GroupSelectionProvider');
  }

  return context;
}
