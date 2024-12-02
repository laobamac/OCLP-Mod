/*
Copyright © 2024 王孝慈

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
*/

#import "Handler.h"
#import "STPrivilegedTask.h"


@implementation Handler

-(void)applicationDidFinishLaunching:(NSNotification *)notification {
    [self performSelectorInBackground:@selector(runProcess) withObject:nil];
}

-(void)createAppWindowWithProgressBar {
    NSRect frame = NSMakeRect(0, 0, 400, 200);
    NSWindow *window = [[NSWindow alloc] initWithContentRect:frame styleMask:(NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskMiniaturizable) backing:NSBackingStoreBuffered defer:NO];
    [window setTitle:@"OCLP-Mod"];
    [window makeKeyAndOrderFront:nil];

    /*
    1. Add AppIcon to top center
    2. Add text below icon: "Installing additional components..."
    3. Add progress bar below text
    */

    NSImageView *iconView = [[NSImageView alloc] initWithFrame:NSMakeRect(150, 95, 100, 100)];
    NSImage *icon = [NSImage imageNamed:@"AppIcon"];
    [iconView setImage:icon];
    [iconView setImageScaling:NSImageScaleProportionallyUpOrDown];
    [iconView setAutoresizingMask:NSViewMinXMargin | NSViewMaxXMargin | NSViewMinYMargin | NSViewMaxYMargin];
    [window.contentView addSubview:iconView];

    NSTextField *textField = [[NSTextField alloc] initWithFrame:NSMakeRect(0, 40, 400, 50)];
    [textField setStringValue:@"正在安装其他组件..."];
    [textField setAlignment:NSTextAlignmentCenter];
    [textField setEditable:NO];
    [textField setBezeled:NO];
    [textField setDrawsBackground:NO];
    [textField setAutoresizingMask:NSViewMinXMargin | NSViewMaxXMargin | NSViewMinYMargin | NSViewMaxYMargin];
    [textField setFont:[NSFont systemFontOfSize:18]];
    [window.contentView addSubview:textField];

    // Set progress bar width to 300
    NSProgressIndicator *progressBar = [[NSProgressIndicator alloc] initWithFrame:NSMakeRect(50, 30, 300, 20)];
    [progressBar setStyle:NSProgressIndicatorStyleBar];
    [progressBar setIndeterminate:YES];
    [progressBar setAutoresizingMask:NSViewMinXMargin | NSViewMaxXMargin | NSViewMinYMargin | NSViewMaxYMargin];
    [progressBar startAnimation:nil];
    [window.contentView addSubview:progressBar];


    // Reference: https://stackoverflow.com/a/61174052
    CGFloat xPos = NSWidth(window.screen.frame) / 2 - NSWidth(window.frame) / 2;
    CGFloat yPos = NSHeight(window.screen.frame) / 2 - NSHeight(window.frame) / 2;

    [window setFrame:NSMakeRect(xPos, yPos, NSWidth(window.frame), NSHeight(window.frame)) display:YES];
}

-(void)spawnProgressWindow {
    dispatch_sync(dispatch_get_main_queue(), ^{
        [self createAppWindowWithProgressBar];
    });
}

-(void)postPKGRunApp:(BOOL)isUpdating {
    NSTask *task = [[NSTask alloc] init];

    [task setLaunchPath:@"/Library/Application Support/laobamac/OCLP-Mod.app/Contents/MacOS/OCLP-Mod"];
    if (isUpdating) {
        [task setArguments:@[@"--update_installed"]];
    }

    [task launch];

    sleep(5);
}

-(void)runProcess {
    int exitCode = 0;
    NSLog(@"Starting...");

    BOOL isInstallingPKG = NO;
    BOOL isUpdating = NO;

    STPrivilegedTask *privilegedTask = [[STPrivilegedTask alloc] init];
    NSArray *components = [[NSProcessInfo processInfo] arguments];
    NSMutableArray *arguments = [NSMutableArray arrayWithArray:components];

    if ([arguments count] == 1 || [arguments[1] isEqualToString:@"--update_installed"]) {
        isInstallingPKG = YES;
        if ([arguments count] != 1) {
            isUpdating = YES;
        }
    }

    if (isInstallingPKG) {

        if (isUpdating) {
            NSLog(@"Updating OCLP-Mod...");
        } else {
            NSLog(@"Installing OCLP-Mod...");
        }

        NSString *pkgPath = [[NSBundle mainBundle] pathForResource:@"OCLP-Mod" ofType:@"pkg"];
        if (!pkgPath) {
            NSLog(@"OCLP-Mod.pkg not found in resources");
            exit(1);
        }
        NSLog(@"Found OCLP-Mod.pkg at %@", pkgPath);

        [arguments removeAllObjects];
        [arguments addObject:@"-pkg"];
        [arguments addObject:pkgPath];
        [arguments addObject:@"-target"];
        [arguments addObject:@"/"];

        [privilegedTask setLaunchPath:@"/usr/sbin/installer"];
        [privilegedTask setArguments:arguments];

        [self spawnProgressWindow];

    } else {
        NSString *launchPath = arguments[1];
        [arguments removeObjectAtIndex:0]; // Remove Binary Path
        [arguments removeObjectAtIndex:0]; // Remove Launch Path
        [privilegedTask setLaunchPath:launchPath];
        [privilegedTask setArguments:arguments];
        [privilegedTask setCurrentDirectoryPath:[[NSBundle mainBundle] resourcePath]];
    }

    OSStatus err = [privilegedTask launch];

    if (err != errAuthorizationSuccess) {
        if (err == errAuthorizationCanceled) {
            NSLog(@"User cancelled");
            exit(1);
        }  else {
            NSLog(@"Something went wrong: %d", (int)err);
            // For error codes, see http://www.opensource.apple.com/source/libsecurity_authorization/libsecurity_authorization-36329/lib/Authorization.h
        }
    }

    // Success! Now, read the output file handle for data
    NSFileHandle *readHandle = [privilegedTask outputFileHandle];
    NSData *outputData = [readHandle readDataToEndOfFile]; // Blocking call
    NSString *outputString = [[NSString alloc] initWithData:outputData encoding:NSUTF8StringEncoding];

    printf("%s", [outputString UTF8String]);

    exitCode = privilegedTask.terminationStatus;
    NSLog(@"Done");

    // If we install the PKG, launch the app
    if (isInstallingPKG) {
        [self postPKGRunApp:isUpdating];
    }

    exit(exitCode);
}

@end
