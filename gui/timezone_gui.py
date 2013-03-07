#! /usr/bin/env python

###############################################################################
# Copyright (c) 2008-2009 VMware, Inc.
#
# This file is part of Weasel.
#
# Weasel is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free
# Software Foundation version 2 and no later version.
#
# Weasel is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License
# version 2 for more details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc., 51
# Franklin St, Fifth Floor, Boston, MA 02110-1301 USA.
#

'''
timezone screen
'''
import os
import time
import math
import gtk
import gobject

import userchoices
from common_windows import CommonWindow
from common_windows import MessageWindow
from singleton import Singleton
from timezone import Timezone, TimezoneList
from signalconnect import connectSignalHandlerByDict
from log import log


IMAGE_DIR = os.path.join('gui', 'images', 'map')

#-----------------------------------------------------------------------------
class PixbufSprite(object):
    '''Convenience class that abstracts pixbuf images and provides
    rectangular coordinates, similar to pygame.sprite.Sprite'''
    def __init__(self, filenameOrPixbuf):
        if type(filenameOrPixbuf) == str:
            self.pixbuf = gtk.gdk.pixbuf_new_from_file(filenameOrPixbuf)
        else:
            self.pixbuf = filenameOrPixbuf
        self.x, self.y = 0,0
        self.width = self.pixbuf.get_width()
        self.height = self.pixbuf.get_height()
        self.visible = True

    def SetCenterX(self, centerx):
        self.x = centerx - (self.width//2)
    def GetCenterX(self):
        return self.x + (self.width//2)
    centerx = property( GetCenterX, SetCenterX )

    def SetCenterY(self, centery):
        self.y = centery - (self.height//2)
    def GetCenterY(self):
        return self.y + (self.height//2)
    centery = property( GetCenterY, SetCenterY )

    def SetTop(self, top):
        self.y = top
    def GetTop(self):
        return self.y
    top = property( GetTop, SetTop )

    def SetBottom(self, bottom):
        self.y = bottom - ( self.height - 1 )
    def GetBottom(self):
        return self.y + ( self.height - 1 )
    bottom = property( GetBottom, SetBottom )

    def SetLeft(self, left):
        self.x = left
    def GetLeft(self):
        return self.x
    left = property( GetLeft, SetLeft )

    def SetRight(self, right):
        self.x = right - ( self.width - 1 )
    def GetRight(self):
        return self.x + ( self.width - 1 )
    right = property( GetRight, SetRight )


    def SetCenter(self, *args):
        ''' can be called like SetCenter( x, y ) or SetCenter( (x,y) )'''
        if len(args) == 1:
            self.centerx = args[0][0]
            self.centery = args[0][1]
        else:
            #note, cast to int so that an exception is thrown if they're
            #not ints (or int-alikes)
            self.centerx = int(args[0])
            self.centery = int(args[1])
    def GetCenter(self):
        return self.centerx, self.centery
    center = property( GetCenter, SetCenter )

    def CollidesWithPoint(self, *args):
        ''' can be called like CollidesWithPoint( x, y )
                            or CollidesWithPoint( (x,y) )
        '''
        if len(args) == 1:
            pointX = args[0][0]
            pointY = args[0][1]
        else:
            pointX = int(args[0])
            pointY = int(args[1])
        collide = (self.left <= pointX <= self.right
                   and self.top <= pointY <= self.bottom)
        return collide

    def DrawOn(self, drawWindow):
        if not self.visible:
            return
        gfxc = drawWindow.new_gc() #graphics context
        drawWindow.draw_pixbuf( gfxc,
                                self.pixbuf,
                                0,0,
                                self.x, self.y,
                                self.width, self.height )


#-----------------------------------------------------------------------------
class PixbufButton(PixbufSprite):
    '''A PixbufSprite that can be hovered over and clicked
    To have the click event do something, hook up a callback with self.clickCB
    '''
    def __init__(self, name):
        self.selected = False
        self.pressed = False
        self.hover = False
        self.name = name
        self.clickCB = None
        
        rootName = os.path.join(IMAGE_DIR, name)
        
        self.imgIdle = gtk.gdk.pixbuf_new_from_file(rootName+'_idle.png')
        self.imgHover = gtk.gdk.pixbuf_new_from_file(rootName+'_hover.png')
        self.imgSelected = gtk.gdk.pixbuf_new_from_file(rootName+'_sel.png')
        self.imgPressed = gtk.gdk.pixbuf_new_from_file(rootName+'_pressed.png')
        
        PixbufSprite.__init__(self, self.imgIdle)
        self.visible = True

    def DrawOn(self, drawWindow):
        if self.pressed:
            self.pixbuf = self.imgPressed
        elif self.selected:
            self.pixbuf = self.imgSelected
        elif self.hover:
            self.pixbuf = self.imgHover
        else:
            self.pixbuf = self.imgIdle
        PixbufSprite.DrawOn(self, drawWindow)

    def HandleMotion(self, pos):
        '''Called whenever the mouse moves.  pos is the mouse position.
        uses self.CollidesWithPoint to determine whether the motion was
        over top of self, or outside'''
        if self.CollidesWithPoint( pos ):
            self.hover = True
        else:
            self.pressed = False
            self.hover = False

    def HandlePress(self, pos):
        self.selected = False
        self.pressed = self.CollidesWithPoint( pos )

    def HandleRelease(self, pos):
        if self.pressed:
            if self.CollidesWithPoint( pos ):
                self.Click( pos )
            self.pressed = False

    def Click(self, pos):
        self.selected = True
        if self.clickCB:
            self.clickCB( self )



#-----------------------------------------------------------------------------
class City(PixbufButton):
    def __init__(self, name, pos):
        PixbufButton.__init__(self, 'city')
        
        self.cityName = name
        self.center = pos
        
    def HandleRelease(self, pos):
        if self.pressed:
            self.Click( pos )
            self.pressed = False

    def DistanceTo(self, pos):
        '''caclulate the distance using the pythagorean theorem.
        a**2 + b**2 = c**2'''
        aLine = self.centerx - pos[0]
        bLine = self.centery - pos[1]
        cLine = math.sqrt( aLine**2 + bLine**2 )
        return cLine

#-----------------------------------------------------------------------------
class CityGroup:
    def __init__(self, tzWindow):
        self.cities = []
        self.tzWindow = tzWindow

    def ClosestCity(self, pos):
        def myCmp(a,b):
            return cmp( a.DistanceTo(pos), b.DistanceTo(pos) )
        self.cities.sort( myCmp )
        return self.cities[0]

    def HandleRelease(self, pos):
        '''Only send the release event through to the closest city'''
        self.ClosestCity(pos).HandleRelease(pos)

    def HandleMotionInside(self, pos):
        for city in self.cities:
            # don't delegate to city.HandleMotion because we don't want
            # two cities to highlight at once (possible because 
            # CollidesWithPoint can be True for both)
            city.hover = False
            if city.pressed:
                city.pressed = False
        closestCity = self.ClosestCity(pos)
        closestCity.hover = True
        self.tzWindow.notifyCityHovered( closestCity )

    def HandleMotionOutside(self, pos):
        for city in self.cities:
            city.HandleMotion(pos)

    def HandlePressInside(self, pos):
        #NOTE: don't let each city calculate its own pressedness.  
        #      Otherwise 2 cities could be pressed at once.  
        #      CityGroup is responsible for pressedness.
        for city in self.cities:
            city.selected = False
        closestCity = self.ClosestCity(pos)
        closestCity.pressed = True

    def HandlePressOutside(self, pos):
        for city in self.cities:
            city.selected = False
            city.pressed = False

    def DrawOn(self, drawWindow):
        for city in self.cities:
            city.DrawOn(drawWindow)


#-----------------------------------------------------------------------------
class OffsetSlice(PixbufButton):
    '''The semi-transparent white area representing a region under one
    timezone offset.
    '''
    def __init__(self, offsetName, pos):
        filePrefix = self.OffsetIdentifierToFilenamePrefix( offsetName )
        PixbufButton.__init__(self, filePrefix)
        self.offsetName = offsetName
        
        self.selected = False
        self.visible = False
        self.pressed = False
        
        self.x, self.y = pos
        
        self.cityGroup = None

        self.pixels = self.imgHover.get_pixels_array()

    def HandleMotion(self, pos):
        PixbufButton.HandleMotion( self, pos )
        if self.cityGroup:
            if self.CollidesWithPoint( pos ):
                self.cityGroup.HandleMotionInside( pos )
            else:
                self.cityGroup.HandleMotionOutside( pos )

    def HandlePress(self, pos):
        PixbufButton.HandlePress( self, pos )
        if self.cityGroup:
            if self.CollidesWithPoint( pos ):
                self.cityGroup.HandlePressInside( pos )
            else:
                self.cityGroup.HandlePressOutside( pos )

    def HandleRelease(self, pos):
        PixbufButton.HandleRelease( self, pos )
        if self.cityGroup:
            self.cityGroup.HandleRelease( pos )


    @staticmethod
    def OffsetIdentifierToFilenamePrefix( offsetID ):
        '''We don't want ugly filenames so transform UTC-06:00 to UTCm0600
        and UTC+06:00 to UTCp0600
        '''
        filePrefix = offsetID.replace(':','')
        filePrefix = filePrefix.replace('+','p')
        filePrefix = filePrefix.replace('-','m')
        return 'zone_slices/'+ filePrefix
        
    def DrawOn(self, drawWindow):
        self.visible = True
        if self.pressed:
            self.pixbuf = self.imgPressed
        elif self.selected:
            self.pixbuf = self.imgSelected
        elif self.hover:
            self.pixbuf = self.imgHover
        else:
            self.visible = False
            return #don't draw self or children
            
        PixbufSprite.DrawOn(self, drawWindow)
        
        if self.cityGroup:
            self.cityGroup.DrawOn(drawWindow)

    def CollidesWithPoint(self, *args):
        #need to make sure they are ints otherwise there will be
        #index error jeopardy below
        if len(args) == 1:
            pointX = int(args[0][0])
            pointY = int(args[0][1])
        else:
            pointX = int(args[0])
            pointY = int(args[1])

        #first see if it is within the bounding rectangle
        if not PixbufSprite.CollidesWithPoint( self, pointX, pointY ):
            return False

        #at this point it must be inside the bounding rectangle
        x = pointX - self.x
        y = pointY - self.y

        def notTransparentOrShadow( pixel ):
            redThreshold   = 250
            greenThreshold = 250
            blueThreshold  = 250
            alphaThreshold = 0
            if int(pixel[0]) > redThreshold and \
               int(pixel[1]) > greenThreshold and \
               int(pixel[2]) > blueThreshold and \
               int(pixel[3]) > alphaThreshold:
                return True
            return False
        return notTransparentOrShadow( self.pixels[y][x] )


#-----------------------------------------------------------------------------
class AdvancedDialog(CommonWindow):
    def __init__(self, xml):
        #TODO: this subclass is not ideal.  We should make it so you can
        # send a glade file or dialog object as an argument to CommonWindow()
        CommonWindow.__init__(self)
        self.dialog = xml.get_widget("tz_advanced")
        self.dialog.set_position(gtk.WIN_POS_CENTER)
        title = self.dialog.get_title() # title comes from glade file
        self.addFrameToWindow(title)

    def hide(self, *args):
        return self.dialog.hide(*args)

    def show(self, *args):
        result = self.dialog.show(*args)
        # can't set cursor until self.dialog has a window.  It doesn't have
        # a window attribute until show() is done
        self.setCursor()
        return result


#-----------------------------------------------------------------------------
# This needs to be a singleton because reloading the sprites takes a 
# long time and a lot of memory.
class TimezoneWindow(Singleton):
    SCREEN_NAME = 'timezone'

    def _singleton_init(self, controlState, xml):
        self.timezones = TimezoneList()
        chosenTZ = userchoices.getTimezone()
        if chosenTZ:
            self.selectedTZ = self.timezones.findByCityName( chosenTZ['city'] )
        else:
            self.selectedTZ = self.timezones.defaultTimezone
        
        connectSignalHandlerByDict(self, TimezoneWindow, xml,
          { ('advanced_ok', 'clicked'): 'onCityListSelect',
            ('advanced_cancel', 'clicked'): 'onCityListCancel',
            ('tz_button', 'clicked'): 'onAdvancedClicked',
            ('TimezoneDrawingArea', 'motion_notify_event'): 'onTZDrawMotion',
            ('TimezoneDrawingArea', 'button_press_event'): 'onTZDrawPress',
            ('TimezoneDrawingArea', 'button_release_event'): 'onTZDrawRelease',
            ('TimezoneDrawingArea', 'expose_event'): 'onTZDrawExpose',
          })
        
        self.tzEntry = xml.get_widget("tz_entry")
        self.advancedDialog = AdvancedDialog(xml)
        self.allTZsView = xml.get_widget("tz_treeview")
        
        self.setupMap(xml)
        self.setupTimezone(xml)

    def __init__(self, controlState, xml):
        controlState.displayHeaderBar = 1
        controlState.windowIcon = 'timezone.png'
        controlState.windowTitle = "Time Zone Settings"
        controlState.windowText = "Select the time zone for ESX"
        
    def prepareAdvancedDialog(self):
        # Note, the Advanced Dialog should be prepared every time before it is 
        # shown, that will set the active city and scroll to it.

        # prepare the TreeView with its model and columns
        allTZsModel = gtk.ListStore(str, str, object)
        self.allTZsView.set_model(allTZsModel)
        if not self.allTZsView.get_columns():
            renderer = gtk.CellRendererText()
            # zoneColumn gets its text from index 0 in the model
            zoneColumn = gtk.TreeViewColumn('Zone Name', renderer, text=0)
            self.allTZsView.append_column(zoneColumn)
            # zoneColumn gets its text from index 1 in the model
            offsetColumn = gtk.TreeViewColumn('UTC Offset', renderer, text=1)
            self.allTZsView.append_column(offsetColumn)
            self.allTZsView.set_search_column(0)

        # populate the model, highlight the selected timezone
        seenZoneNames = []
        for index, tz in enumerate(self.timezones.sortedIter()):
            if tz.zoneName in seenZoneNames:
                continue # don't show duplicate zone names
            seenZoneNames.append(tz.zoneName)

            allTZsModel.append((tz.zoneName, tz.offset, tz))
            if self.selectedTZ == tz:
                # NOTE, this "cursor" is the highlighted row, not the mouse
                self.allTZsView.set_cursor(index)
                self.allTZsView.scroll_to_cell(index, None, True, 0.5)

    def setupTimezone(self, xml):
        self.tzEntry.set_text(self.selectedTZ.zoneName)

    def setupMap(self, xml):
        self.cityHoverLabel = xml.get_widget("hover_label")
        self.drawingArea = xml.get_widget("TimezoneDrawingArea")
        
        bgFileName = os.path.join(IMAGE_DIR, 'background.png')
        self.bgImage = PixbufSprite(bgFileName)
        
        bgFileName = os.path.join(IMAGE_DIR, 'map.png')
        self.mapImage = PixbufSprite(bgFileName)
        
        self.sprites = [
                        self.bgImage,
                        self.mapImage,
                       ] #note: order is important.  it is the drawing order
        self.listeners= [] #note: order is important.  (event handling order)
        

        def placeCityDot(tz, clickCB, offsetSlice, isSelected):
            if not tz.cityPos:
                return #this city doesn't have a place on the map
            city = City(tz.city, tz.cityPos)
            city.clickCB = clickCB
            offsetSlice.cityGroup.cities.append(city)
            if isSelected:
                offsetSlice.selected = True
                city.selected = True

        offsetSlicesByName = {}
        secondPass = []
        for tzList in self.timezones.groupByOffsets().values():
            
            offsetName = tzList[0].offset
            offsetPos = tzList[0].offsetPos
            if not offsetPos:
                secondPass += [tz for tz in tzList
                               if tz.showAsMapOffset]
                continue #this offset doesn't have a place on the map

            offsetSlice = OffsetSlice(offsetName, offsetPos)
            offsetSlice.cityGroup = CityGroup(self)
            offsetSlice.clickCB = self.onOffsetSliceClick
            offsetSlicesByName[offsetName] = offsetSlice

            for tz in tzList:
                isSelected = (tz == self.selectedTZ)
                placeCityDot(tz, self.onCityClick, offsetSlice, isSelected)
            
            self.sprites.append(offsetSlice)
            self.listeners.append(offsetSlice)

        # Second pass: collect those cities important enough to be on
        # the map, but whose offset is weird, so we put them in the slice
        # that best approximates it.
        for tz in secondPass:
            offsetSlice = offsetSlicesByName.get(tz.showAsMapOffset, None)
            if not offsetSlice:
                log.warn('Offset %s not on the map.  TZ %s could not be drawn'
                         % (tz.showAsMapOffset, tz.zoneName))
                continue
            isSelected = (tz == self.selectedTZ)
            placeCityDot(tz, self.onCityClick, offsetSlice, isSelected)


    def notifyCityHovered(self, city):
        self.cityHoverLabel.set_text( city.cityName )

    def drawAll(self):
        for sprite in self.sprites:
            sprite.DrawOn( self.drawWindow )

    def onCityListCancel(self, widget, *args):
        self.advancedDialog.hide()

    def onAdvancedClicked(self, *args):
        self.prepareAdvancedDialog()
        self.advancedDialog.show()

    def onCityListSelect(self, widget, *args):
        model, treeIter = self.allTZsView.get_selection().get_selected()
        if not treeIter:
            MessageWindow(None, "Invalid Time Zone",
                "You must select a time zone.")
            return
        zoneName, offset, tz = model[treeIter]
        self.selectedTZ = tz

        log.debug('TZ %s chosen from list.' % str(tz))
        self.tzEntry.set_text(tz.zoneName)
        for sprite in self.sprites:
            if not isinstance(sprite, OffsetSlice):
                continue
            if sprite.offsetName in [tz.offset, tz.showAsMapOffset]:
                sprite.selected = True
            else:
                sprite.selected = False
            for citySprite in sprite.cityGroup.cities:
                if citySprite.cityName == tz.city:
                    citySprite.selected = True
                else:
                    citySprite.selected = False

        self.advancedDialog.hide()
        self.drawingArea.queue_draw()


    def onOffsetSliceClick(self, offsetSlice):
        # current behaviour is for the city closest to the mouse to be
        # always highlighted, so an offset will never get a click by 
        # itself.  Therefore, pass.
        return

    def onCityClick(self, city):
        log.debug( 'onCityClick %s' % (city.cityName) )
        tz = self.timezones.findByCityName( city.cityName )
        self.tzEntry.set_text(tz.zoneName)
        self.selectedTZ = tz

    def onTZDrawExpose(self, *args):
        self.drawWindow = self.drawingArea.window
        assert self.drawWindow
        self.drawAll()
        #return False

    def onTZDrawMotion(self, widget, event):
        self.cityHoverLabel.set_text('')
        for listener in self.listeners:
            if hasattr(listener, 'HandleMotion'):
                listener.HandleMotion( (event.x, event.y) )

        self.drawingArea.queue_draw()

    def onTZDrawPress(self, widget, event):
        log.debug( 'Press at %d %d' % (event.x, event.y) )
        for listener in self.listeners:
            if hasattr(listener, 'HandlePress'):
                listener.HandlePress( (event.x, event.y) )

        self.drawingArea.queue_draw()

    def onTZDrawRelease(self, widget, event):
        log.debug( 'Release at %d %d' % (event.x, event.y) )
        for listener in self.listeners:
            if hasattr(listener, 'HandleRelease'):
                listener.HandleRelease( (event.x, event.y) )

        self.drawingArea.queue_draw()

    def getNext(self):
        tz = self.selectedTZ
        userchoices.setTimezone(tz.zoneName, tz.offset, tz.city)
        tz.runtimeAction()


