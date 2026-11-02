import { Component, Input, Output, EventEmitter, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IconComponent } from '../../../../../../shared/components/icon/icon.component';
import { IamUserService } from '../../../../../../core/services/iam-user.service';
import { DialogService } from '../../../../../../core/services/dialog.service';
import { LoadingService } from '../../../../../../core/services/loading.service';
import { GlobalUserItem, GlobalUserCreatePayload } from '../../../../../../core/models/iam-user.model';

@Component({
  selector: 'app-create-user-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent],
  templateUrl: './create-user-dialog.component.html',
  styleUrl: './create-user-dialog.component.scss'
})
export class CreateUserDialogComponent implements OnInit {
  @Input() user: GlobalUserItem | null = null;
  @Output() saved = new EventEmitter<GlobalUserItem | void>();
  @Output() closed = new EventEmitter<void>();

  private userService = inject(IamUserService);
  private dialogs = inject(DialogService);
  private loading = inject(LoadingService);

  readonly isSubmitting = signal<boolean>(false);
  readonly showPassword = signal<boolean>(false);

  // Form Fields
  userId: string = '';
  firstName: string = '';
  middleName: string = '';
  lastName: string = '';
  email: string = '';
  password: string = 'Urban@2026';
  mobileNumber: string = '';
  idpProvider: string = 'Keycloak Suvidha';
  externalIdentityId: string = '';
  userType: string = 'Internal Staff';
  accountStatus: string = 'Active';
  preferredLanguage: string = 'English';
  timeZone: string = 'Asia/Kolkata';
  employeeId: string = '';
  designation: string = '';
  department: string = '';
  profilePhotoUrl: string = '';
  accountExpiryDate: string = '';
  remarks: string = '';

  readonly idpProviders = [
    'Keycloak Suvidha',
    'MeriPehchan',
    'Aadhaar e-Pramaan',
    'Jan Parichay',
    'NIC SSO',
    'Google Workspace'
  ];

  readonly userTypes = [
    'Internal Staff',
    'Government Officer',
    'Support Staff',
    'Auditor',
    'External Partner'
  ];

  readonly accountStatuses = [
    'Active',
    'Suspended',
    'Pending Invitation',
    'Deactivated'
  ];

  readonly departments = [
    'Executive Administration',
    'Directorate of Municipal Administration',
    'Revenue & Property Tax',
    'Water Supply & Sewerage',
    'Town Planning & Regulation',
    'Finance & Accounts',
    'Public Health & Sanitation',
    'Engineering & Infrastructure',
    'Audit & Vigilance'
  ];

  ngOnInit(): void {
    if (this.user) {
      this.userId = this.user.id;
      this.firstName = this.user.firstName;
      this.middleName = this.user.middleName || '';
      this.lastName = this.user.lastName;
      this.email = this.user.email;
      this.mobileNumber = this.user.mobileNumber || '';
      this.idpProvider = this.user.idpProvider;
      this.externalIdentityId = this.user.externalIdentityId || '';
      this.userType = this.user.userType;
      this.accountStatus = this.user.accountStatus;
      this.preferredLanguage = this.user.preferredLanguage || 'English';
      this.timeZone = this.user.timeZone || 'Asia/Kolkata';
      this.employeeId = this.user.employeeId || '';
      this.designation = this.user.designation || '';
      this.department = this.user.department || '';
      this.profilePhotoUrl = this.user.profilePhotoUrl || '';
      this.accountExpiryDate = this.user.accountExpiryDate || '';
      this.remarks = this.user.remarks || '';
    } else {
      this.userId = 'Auto-assigned (UUID v4)';
    }
  }

  generateRandomPassword(): void {
    const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789!@#$%';
    let res = '';
    for (let i = 0; i < 10; i++) {
      res += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    this.password = res;
    this.showPassword.set(true);
    this.dialogs.showToast('Generated strong password', 'info');
  }

  onSubmit(): void {
    if (!this.firstName.trim() || !this.lastName.trim() || !this.email.trim()) {
      this.dialogs.showToast('Please fill all required profile fields (First Name, Last Name, Email)', 'warning');
      return;
    }

    const payload: GlobalUserCreatePayload = {
      firstName: this.firstName.trim(),
      middleName: this.middleName.trim() || null,
      lastName: this.lastName.trim(),
      email: this.email.trim().toLowerCase(),
      password: this.password?.trim() || 'Urban@2026',
      mobileNumber: this.mobileNumber.trim() || null,
      idpProvider: this.idpProvider,
      externalIdentityId: this.externalIdentityId.trim() || null,
      userType: this.userType,
      accountStatus: this.accountStatus,
      preferredLanguage: this.preferredLanguage,
      timeZone: this.timeZone,
      employeeId: this.employeeId.trim() || null,
      designation: this.designation.trim() || null,
      department: this.department || null,
      profilePhotoUrl: this.profilePhotoUrl.trim() || null,
      accountExpiryDate: this.accountExpiryDate || null,
      remarks: this.remarks.trim() || null
    };

    this.isSubmitting.set(true);
    if (this.user) {
      this.loading.show('Updating user profile...');
      this.userService.updateUser(this.user.id, payload).subscribe({
        next: (res) => {
          this.isSubmitting.set(false);
          this.loading.hide();
          if (res.success) {
            this.dialogs.showToast(`User '${res.data.fullName}' updated`, 'success');
            this.saved.emit();
          }
        },
        error: (err) => {
          this.isSubmitting.set(false);
          this.loading.hide();
          this.dialogs.showToast(err?.error?.detail || 'Failed to update user', 'error');
        }
      });
    } else {
      this.loading.show('Creating user in directory...');
      this.userService.createUser(payload).subscribe({
        next: (res) => {
          this.isSubmitting.set(false);
          this.loading.hide();
          if (res.success) {
            this.dialogs.showToast(`User '${res.data.fullName}' created successfully`, 'success');
            this.saved.emit(res.data);
          }
        },
        error: (err) => {
          this.isSubmitting.set(false);
          this.loading.hide();
          this.dialogs.showToast(err?.error?.detail || 'Failed to create user', 'error');
        }
      });
    }
  }

  onCancel(): void {
    this.closed.emit();
  }
}

