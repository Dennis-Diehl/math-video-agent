"use client";

import Drawer from "@mui/material/Drawer";
import Box from "@mui/material/Box";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemText from "@mui/material/ListItemText";
import IconButton from "@mui/material/IconButton";
import Button from "@mui/material/Button";
import Typography from "@mui/material/Typography";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import AddIcon from "@mui/icons-material/Add";
import CloseIcon from "@mui/icons-material/Close";
import type { HistoryEntry } from "@/types";

const EXPANDED_WIDTH = 240;
const COLLAPSED_WIDTH = 56;

interface SidebarProps {
  entries: HistoryEntry[];
  activeJobId: string | null;
  onNewProblem: () => void;
  onSelect: (jobId: string) => void;
  onDelete: (jobId: string) => void;
  collapsed?: boolean;
  onCollapsedChange?: (collapsed: boolean) => void;
  mobile?: boolean;
}

export function Sidebar({
  entries,
  activeJobId,
  onNewProblem,
  onSelect,
  onDelete,
  collapsed = false,
  onCollapsedChange = () => {},
  mobile = false,
}: SidebarProps) {
  const width = collapsed ? COLLAPSED_WIDTH : EXPANDED_WIDTH;

  const content = (
    <Box
      sx={{
        overflowX: "hidden",
        height: "100%",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <Box
        sx={{
          display: "flex",
          flexDirection: "column",
          alignItems: collapsed ? "center" : "stretch",
          gap: 1,
          p: 1.5,
        }}
      >
        <IconButton
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          onClick={() => onCollapsedChange(!collapsed)}
          size="small"
          sx={{ alignSelf: collapsed ? "center" : "flex-end" }}
        >
          {collapsed ? <ChevronRightIcon fontSize="small" /> : <ChevronLeftIcon fontSize="small" />}
        </IconButton>
        <Button
          onClick={onNewProblem}
          variant="contained"
          startIcon={collapsed ? undefined : <AddIcon />}
          sx={collapsed ? { minWidth: 0, p: 1 } : undefined}
        >
          {collapsed ? <AddIcon fontSize="small" /> : "New problem"}
        </Button>
      </Box>
      <Box
        data-testid="sidebar-history-section"
        aria-hidden={collapsed}
        inert={collapsed || undefined}
        sx={{
          flex: 1,
          overflow: "auto",
          opacity: collapsed ? 0 : 1,
          transition: (t) => t.transitions.create("opacity"),
          px: 1,
        }}
      >
        <Typography variant="overline" sx={{ px: 1 }}>
          History
        </Typography>
        <List dense>
          {entries.map((entry) => (
            <ListItem
              key={entry.jobId}
              disablePadding
              sx={{ borderRadius: 1, mb: 0.5 }}
              secondaryAction={
                <IconButton
                  aria-label={`Delete ${entry.problem} (${entry.jobId.slice(0, 8)})`}
                  onClick={() => onDelete(entry.jobId)}
                  size="small"
                  edge="end"
                >
                  <CloseIcon fontSize="inherit" />
                </IconButton>
              }
            >
              <ListItemButton
                data-testid={`history-entry-${entry.jobId}`}
                data-unread={entry.unread}
                selected={entry.jobId === activeJobId}
                onClick={() => onSelect(entry.jobId)}
              >
                <ListItemText slotProps={{ primary: { noWrap: true } }}>{entry.problem}</ListItemText>
              </ListItemButton>
            </ListItem>
          ))}
        </List>
      </Box>
    </Box>
  );

  if (mobile) {
    return (
      <Drawer
        variant="temporary"
        open={!collapsed}
        onClose={() => onCollapsedChange(true)}
        sx={{ "& .MuiDrawer-paper": { width: EXPANDED_WIDTH } }}
      >
        {content}
      </Drawer>
    );
  }

  return (
    <Drawer
      variant="permanent"
      sx={{
        width,
        flexShrink: 0,
        "& .MuiDrawer-paper": {
          position: "relative",
          width,
          boxSizing: "border-box",
          transition: (t) => t.transitions.create("width"),
        },
      }}
    >
      {content}
    </Drawer>
  );
}
