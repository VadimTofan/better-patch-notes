local _, addon = ...

local function newDatabase()
    return {
        schemaVersion = 2,
        seen = {},
        sharedSeen = {},
        lastShownAddonVersion = "",
        window = {
            point = "CENTER",
            x = 0,
            y = 0,
        },
        minimap = {
            hidden = false,
            angle = 220,
        },
    }
end

local function sanitizeMinimap(database)
    if type(database.minimap) ~= "table" then
        database.minimap = newDatabase().minimap
        return
    end

    if type(database.minimap.hidden) ~= "boolean" then
        database.minimap.hidden = false
    end
    if type(database.minimap.angle) ~= "number" then
        database.minimap.angle = 220
    end
end

local function sanitizeWindow(database)
    if type(database.window) ~= "table" then
        database.window = newDatabase().window
        return
    end

    if type(database.window.point) ~= "string" then
        database.window.point = "CENTER"
    end
    if type(database.window.x) ~= "number" then
        database.window.x = 0
    end
    if type(database.window.y) ~= "number" then
        database.window.y = 0
    end
end

function addon.InitializeState()
    if type(BetterPatchNotesDB) ~= "table" then
        BetterPatchNotesDB = newDatabase()
    end

    BetterPatchNotesDB.schemaVersion = 2
    if type(BetterPatchNotesDB.seen) ~= "table" then
        BetterPatchNotesDB.seen = {}
    end
    if type(BetterPatchNotesDB.sharedSeen) ~= "table" then
        BetterPatchNotesDB.sharedSeen = {}
    end
    if type(BetterPatchNotesDB.lastShownAddonVersion) ~= "string" then
        BetterPatchNotesDB.lastShownAddonVersion = ""
    end
    sanitizeWindow(BetterPatchNotesDB)
    sanitizeMinimap(BetterPatchNotesDB)
    addon.db = BetterPatchNotesDB
end

function addon.HasUnseenAddonVersion()
    return addon.db.lastShownAddonVersion ~= addon.version
end

function addon.MarkAddonVersionShown()
    addon.db.lastShownAddonVersion = addon.version
end

local function classSeen(classToken)
    local seen = addon.db.seen[classToken]
    if type(seen) ~= "table" then
        seen = {}
        addon.db.seen[classToken] = seen
    end

    return seen
end

function addon.HasUnseen(classToken, channel)
    local versions = addon.PatchNotesData.classChannelVersions[classToken]
    local version = versions[channel]
    if version == "" then
        return false
    end

    return classSeen(classToken)[channel] ~= version
end

function addon.HasUnseenShared(channel)
    local version = addon.PatchNotesData.sharedChannelVersions[channel]
    if version == "" then
        return false
    end

    return addon.db.sharedSeen[channel] ~= version
end

function addon.MarkChannelSeen(classToken, channel)
    local seen = classSeen(classToken)
    local versions = addon.PatchNotesData.classChannelVersions[classToken]
    seen[channel] = versions[channel]
    addon.db.sharedSeen[channel] =
        addon.PatchNotesData.sharedChannelVersions[channel]
end

local function latestDate(classDate, sharedDate)
    classDate = classDate or ""
    sharedDate = sharedDate or ""
    if sharedDate > classDate then
        return sharedDate
    end

    return classDate
end

function addon.SelectInitialChannel(classToken)
    local liveUnseen = addon.HasUnseen(classToken, "live")
        or addon.HasUnseenShared("live")
    local ptrUnseen = addon.HasUnseen(classToken, "ptr")
        or addon.HasUnseenShared("ptr")

    if liveUnseen and ptrUnseen then
        local classDates = addon.PatchNotesData.classLatestDates[classToken]
        local sharedDates = addon.PatchNotesData.sharedLatestDates
        local liveDate = latestDate(classDates.live, sharedDates.live)
        local ptrDate = latestDate(classDates.ptr, sharedDates.ptr)
        if ptrDate > liveDate then
            return "ptr"
        end

        return "live"
    end
    if ptrUnseen then
        return "ptr"
    end

    return "live"
end
