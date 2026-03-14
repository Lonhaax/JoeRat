namespace CSharpSender;

partial class Form1
{
    /// <summary>
    ///  Required designer variable.
    /// </summary>
    private System.ComponentModel.IContainer components = null;
    private System.Windows.Forms.TextBox txtWebSocket;
    private System.Windows.Forms.TextBox txtRoomId;
    private System.Windows.Forms.TextBox txtSecret;
    private System.Windows.Forms.Button btnStart;
    private System.Windows.Forms.Button btnStop;
    private System.Windows.Forms.Label lblStatus;

    /// <summary>
    ///  Clean up any resources being used.
    /// </summary>
    /// <param name="disposing">true if managed resources should be disposed; otherwise, false.</param>
    protected override void Dispose(bool disposing)
    {
        if (disposing && (components != null))
        {
            components.Dispose();
        }
        base.Dispose(disposing);
    }

    #region Windows Form Designer generated code

    /// <summary>
    ///  Required method for Designer support - do not modify
    ///  the contents of this method with the code editor.
    /// </summary>
    private void InitializeComponent()
    {
        components = new System.ComponentModel.Container();
        this.txtWebSocket = new System.Windows.Forms.TextBox();
        this.txtRoomId = new System.Windows.Forms.TextBox();
        this.txtSecret = new System.Windows.Forms.TextBox();
        this.btnStart = new System.Windows.Forms.Button();
        this.btnStop = new System.Windows.Forms.Button();
        this.lblStatus = new System.Windows.Forms.Label();
        // txtWebSocket
        this.txtWebSocket.Location = new System.Drawing.Point(20, 20);
        this.txtWebSocket.Size = new System.Drawing.Size(400, 23);
        this.txtWebSocket.Text = "ws://vnc.jake.cash:3000";
        this.txtWebSocket.PlaceholderText = "ws://host:3000 or wss://host:3000";
        // txtRoomId
        this.txtRoomId.Location = new System.Drawing.Point(20, 55);
        this.txtRoomId.Size = new System.Drawing.Size(180, 23);
        this.txtRoomId.Text = "ops-room";
        this.txtRoomId.PlaceholderText = "Room ID";
        // txtSecret
        this.txtSecret.Location = new System.Drawing.Point(210, 55);
        this.txtSecret.Size = new System.Drawing.Size(210, 23);
        this.txtSecret.Text = "boi123";
        this.txtSecret.PlaceholderText = "Secret";
        this.txtSecret.UseSystemPasswordChar = true;
        // btnStart
        this.btnStart.Location = new System.Drawing.Point(20, 90);
        this.btnStart.Size = new System.Drawing.Size(100, 30);
        this.btnStart.Text = "Start";
        // btnStop
        this.btnStop.Location = new System.Drawing.Point(140, 90);
        this.btnStop.Size = new System.Drawing.Size(100, 30);
        this.btnStop.Text = "Stop";
        // lblStatus
        this.lblStatus.Location = new System.Drawing.Point(20, 135);
        this.lblStatus.Size = new System.Drawing.Size(400, 23);
        this.lblStatus.Text = "Status: Idle";
        // Add controls
        this.Controls.Add(this.txtWebSocket);
        this.Controls.Add(this.txtRoomId);
        this.Controls.Add(this.txtSecret);
        this.Controls.Add(this.btnStart);
        this.Controls.Add(this.btnStop);
        this.Controls.Add(this.lblStatus);
        AutoScaleMode = AutoScaleMode.Font;
        ClientSize = new Size(800, 450);
        Text = "Screen Sender";
    }

    #endregion
}
